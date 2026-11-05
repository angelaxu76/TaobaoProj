# -*- coding: utf-8 -*-
"""
用 LaMa 把长方形图片自然扩展成正方形：不裁切原图，两侧（或上下）空白由模型按背景纹理补全。

模型：models/big-lama.pt（TorchScript，直接用 torch 加载；不装 simple-lama-inpainting，
它要求 numpy<2 / pillow<10，会把项目依赖降级）。
下载：https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt
      md5 = e3aa4aaa15225a33ec84f9f4bc47e500

做法：
  1) 原图居中放到正方形画布，空白区域作为 mask
  2) 画布外再加一圈纯色参照（CONTEXT_MARGIN，每侧取原图边缘的中位色），把 mask 包在已知内容中间。
     LaMa 训练时修的是图片内部的洞，mask 直接贴画布边缘时没有外侧参照，
     补出来的区域亮度会漂移（接缝明显），角落还会凭空长出深色斑块。
     这里不能逐行复制边缘像素：主体贴边时（如大衣）会被拉成横向条纹
  3) 缩到 WORK_SIZE 跑 LaMa（CPU 可接受的速度，大范围补全的结构也比原分辨率好）
  4) 裁掉外圈，放大回原尺寸，只取补出来的区域；原图像素保持不变，接缝羽化过渡

调用方式：
    from helper.image.expand_square_lama import batch_expand_square
    batch_expand_square(src_dir, dst_dir)
"""
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
import torch
from PIL import Image, ImageFilter

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "big-lama.pt"

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
WORK_SIZE = 1024      # LaMa 推理边长；越大越慢，纹理更细但大范围结构更容易重复
CONTEXT_MARGIN = 64   # 画布外参照圈宽度（WORK_SIZE 分辨率下的像素），推理后裁掉
EDGE_INSET = 4        # mask 向原图内部多吃的像素（WORK_SIZE 分辨率）：部分原图最外侧有几列亮边，一并重新生成
EDGE_BAND = 20        # 取边缘中位色的条带宽度（WORK_SIZE 分辨率），从 EDGE_INSET 往里取
FEATHER = 12          # 接缝羽化宽度（原图分辨率下的像素）
JPEG_QUALITY = 90

_model = None


def _get_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"找不到 LaMa 模型：{MODEL_PATH}（下载地址见文件头注释）")
        print(f"⏳ 加载 LaMa 模型：{MODEL_PATH.name}")
        _model = torch.jit.load(str(MODEL_PATH), map_location="cpu").eval()
    return _model


def _inpaint(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """rgb: HxWx3 uint8；mask: HxW，>0 为待补全区域。返回同尺寸 uint8。"""
    h, w = mask.shape
    pad_h, pad_w = -h % 8, -w % 8   # 模型要求宽高是 8 的倍数
    rgb_p = np.pad(rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="symmetric")
    mask_p = np.pad(mask, ((0, pad_h), (0, pad_w)), mode="symmetric")

    image_t = torch.from_numpy(rgb_p).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    mask_t = torch.from_numpy((mask_p > 0).astype("float32")).unsqueeze(0).unsqueeze(0)
    with torch.inference_mode():
        out = _get_model()(image_t, mask_t)
    res = out[0].permute(1, 2, 0).numpy()
    return np.clip(res * 255, 0, 255).astype("uint8")[:h, :w]


def _median_color(band: np.ndarray) -> np.ndarray:
    return np.median(band.reshape(-1, 3), axis=0).astype("uint8")


def expand_to_square_lama(
    img: Image.Image, work_size: int = WORK_SIZE, feather: int = FEATHER
) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    if w == h:
        return img
    side = max(w, h)
    x0, y0 = (side - w) // 2, (side - h) // 2

    # 缩小后的画布 + mask
    scale = min(1.0, work_size / side)
    s_side = int(round(side * scale))
    s_w, s_h = int(round(w * scale)), int(round(h * scale))
    s_x0, s_y0 = (s_side - s_w) // 2, (s_side - s_h) // 2

    m, i, b = CONTEXT_MARGIN, EDGE_INSET, EDGE_BAND
    photo = np.asarray(img.resize((s_w, s_h), Image.LANCZOS))
    top, left = s_y0 + m, s_x0 + m
    bottom, right = s_side - s_h - s_y0 + m, s_side - s_w - s_x0 + m
    canvas = np.pad(photo, ((top, bottom), (left, right), (0, 0)), mode="edge")

    # 扩展方向的外侧换成纯色参照；mask 覆盖补全区域，并向原图内部多吃 EDGE_INSET
    mask = np.zeros(canvas.shape[:2], dtype="uint8")
    mask[m:m + s_side, m:m + s_side] = 255
    if w < h:
        canvas[:, :left] = _median_color(photo[:, i:i + b])
        canvas[:, left + s_w:] = _median_color(photo[:, -(i + b):-i])
        mask[top:top + s_h, left + i:left + s_w - i] = 0
    else:
        canvas[:top] = _median_color(photo[i:i + b])
        canvas[top + s_h:] = _median_color(photo[-(i + b):-i])
        mask[top + i:top + s_h - i, left:left + s_w] = 0

    filled = Image.fromarray(_inpaint(canvas, mask)[m:m + s_side, m:m + s_side])
    result = filled.resize((side, side), Image.LANCZOS)

    # 原图盖回去，向内羽化，避免接缝；从 mask 吃进去的位置再往里开始，原图外侧的亮边不保留
    inner = feather + int(np.ceil(EDGE_INSET / scale))
    alpha = Image.new("L", (side, side), 0)
    if w < h:
        alpha.paste(255, (x0 + inner, 0, x0 + w - inner, side))
    else:
        alpha.paste(255, (0, y0 + inner, side, y0 + h - inner))
    alpha = alpha.filter(ImageFilter.GaussianBlur(feather / 2))

    orig_layer = result.copy()
    orig_layer.paste(img, (x0, y0))
    return Image.composite(orig_layer, result, alpha)


def batch_expand_square(
    input_dir,
    output_dir,
    work_size: int = WORK_SIZE,
    quality: int = JPEG_QUALITY,
    post_process: Optional[Callable[[Image.Image], Image.Image]] = None,
) -> Tuple[int, int]:
    """
    批量扩展，输出同名 JPG（已存在的覆盖）。
    post_process：可选，对扩展后的图片再做一步处理（Image -> Image）。
    """
    src, dst = Path(input_dir), Path(output_dir)
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)
    print(f"🖼️ LaMa 扩展正方形：{src}，共 {len(files)} 张")

    ok = fail = 0
    t0 = time.time()
    for i, p in enumerate(files, 1):
        out_path = dst / f"{p.stem}.jpg"
        try:
            with Image.open(p) as img:
                square = expand_to_square_lama(img, work_size=work_size)
            if post_process:
                square = post_process(square)
            square.save(out_path, "JPEG", quality=quality, optimize=True)
            ok += 1
            print(f"  ✅ [{i}/{len(files)}] {p.name}")
        except Exception as e:
            fail += 1
            print(f"  ❌ {p.name}: {e}")

    print(f"完成：成功 {ok}，失败 {fail}，耗时 {time.time() - t0:.1f}s")
    return ok, fail
