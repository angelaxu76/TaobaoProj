# -*- coding: utf-8 -*-
"""
cut_square_white_watermark.py  —  透明保留到最后一步，再压白底转 JPG
流程：
  1) 必要时自动抠图（remove.bg API 优先；本地 rembg 备用）
  2) 按 alpha 或白边精裁
  3) 正方形居中：有透明->RGBA透明画布；无透明->RGB白底
  4) 水印：全程 RGBA 合成，不丢透明
  5) 最终一次性压到白底 -> 保存 JPG（可选同步保存透明 PNG）
"""

import io, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops

# ================== 配置 ==================
INPUT_DIR  = r"D:\TB\Products\barbour\facewap\faceswap_output-men\faceswap_output"
OUTPUT_DIR = r"D:\TB\Products\barbour\facewap\faceswap_processed"

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
TARGET_SIZE: Optional[int] = 1200      # 统一输出边长；None 不缩放
CANVAS_COLOR = (255, 255, 255)         # 白底颜色
OUTPUT_JPEG_QUALITY = 95
SAVE_TRANSPARENT_PNG = False           # 需要同时导出透明 PNG 时 True

# 自动抠图
AUTO_CUTOUT = True                     # 关掉可快速验证非抠图流程

# ── 抠图后端选择 ──
# "rembg"    本地 rembg（默认，无需额外安装）
# "bria"     本地 BRIA RMBG-2.0（免费最佳质量；需 pip install transformers torch torchvision）
# "removebg" remove.bg API（商业级精度；需填写下方 REMOVEBG_API_KEY）
CUTOUT_BACKEND = "rembg"

# ── remove.bg API（CUTOUT_BACKEND="removebg" 时生效）──
# 注册：https://www.remove.bg/zh/dashboard#api-key  50张/月免费
REMOVEBG_API_KEY = ""
# "regular"=标准(1积分) | "hd"=高清4K(10积分，边缘更精细，服装推荐)
REMOVEBG_SIZE = "regular"

# ── 本地 rembg（CUTOUT_BACKEND="rembg" 时生效）──
MODEL_NAME = "birefnet-general"        # birefnet-general(通用) | birefnet-fashion(服装专用) | birefnet-massive(最大)

# 白底检测（跳过已是白底的图）
WHITE_BG_SKIP  = True    # True=检测到白底就跳过抠图；False=全部强制抠图
WHITE_BG_TOL   = 15      # 255-tol 以上算白色（越小越严格）
WHITE_BG_PATCH = 0.04    # 角落采样区域占短边的比例

# 白毛边处理（强烈建议开启）
DEFRINGE_WHITE = True    # 逆混合去除白底残留：从半透明边缘像素中移除白底污染
ALPHA_ERODE    = 1       # alpha 侵蚀像素数（0=不侵蚀；1=轻度去毛边；2=更干净但可能损失细节）
# 形态学闭运算：填充 alpha 内部空洞（解决衣服底部/衣领被误抠变白问题）
# 原理：先膨胀 N 次再腐蚀 N 次，填补前景内部的小空洞而不扩大外边缘
# 0=不做；3=适度填补；5=填补较大空洞（服装下摆）；建议值：3~5
ALPHA_CLOSING  = 5

# rembg alpha matting（需要 pip install pymatting；对发丝/毛发类有效，服装类影响不大）
ALPHA_MATTING  = False
ALPHA_MATTING_FG_THRESHOLD = 240
ALPHA_MATTING_BG_THRESHOLD = 10
ALPHA_MATTING_ERODE_SIZE   = 10

# 斜纹整幅水印
DIAGONAL_TEXT_ENABLE = True
DIAGONAL_TEXT = "英国哈梅尔百货"
DIAGONAL_ALPHA = 30
DIAGONAL_FONT_SIZE_RATIO = 0.02
DIAGONAL_STEP_RATIO = 0.50
DIAGONAL_ANGLE_DEG = -30

# 右下角小字水印
LOCAL_LOGO_ENABLE = True
LOCAL_LOGO_TEXT = "英国哈梅尔百货"
LOCAL_FONT_SIZE_RATIO = 0.04
LOCAL_MARGIN_RATIO = 0.03
LOCAL_BG_ALPHA = 96
LOCAL_TEXT_ALPHA = 40

# 多线程
# rembg 的 ONNX session 推理是线程安全的；建议 AUTO_CUTOUT=True 时 MAX_WORKERS ≤ 4
# remove.bg API 可适当提高并发（受网络和 API 限速影响）
MAX_WORKERS = 4

FONT_PATH = None  # 如 r"C:\Windows\Fonts\msyh.ttc"

# ================== 工具函数 ==================
def _get_font(px: int):
    try:
        if FONT_PATH:
            return ImageFont.truetype(FONT_PATH, px)
        for name in ["msyh.ttc", "simhei.ttf", "arial.ttf"]:
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                pass
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("LA", "RGBA", "PA") or ("transparency" in img.info)

def _autocrop_by_alpha(img: Image.Image, thr: int = 5) -> Image.Image:
    """按 alpha 精裁透明边"""
    if not _has_alpha(img):
        return img
    rgba = img.convert("RGBA")
    a = np.array(rgba.split()[-1])
    mask = a > thr
    if not mask.any():
        return rgba
    ys, xs = np.where(mask)
    y1, y2 = ys.min(), ys.max() + 1
    x1, x2 = xs.min(), xs.max() + 1
    return rgba.crop((x1, y1, x2, y2))

def _autocrop_white_border(img: Image.Image, tol: int = 8) -> Image.Image:
    """对无透明图，仅裁四周近白空边（保守）"""
    if _has_alpha(img):
        return img
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, CANVAS_COLOR)
    diff = ImageChops.difference(rgb, bg)
    diff = ImageChops.add(diff, diff, 2.0, -tol)
    bbox = diff.getbbox()
    return rgb.crop(bbox) if bbox else rgb

def _pad_to_square(img: Image.Image, target_size: Optional[int]) -> Image.Image:
    """
    正方形居中：有透明->RGBA透明画布；无透明->RGB白底。
    注意：这里不把 RGBA 转成 RGB，保持透明到后续水印阶段。
    """
    has_alpha = _has_alpha(img)
    mode = "RGBA" if has_alpha else "RGB"
    bg   = (0, 0, 0, 0) if has_alpha else CANVAS_COLOR

    img = img.convert(mode)
    w, h = img.size
    side = max(w, h)

    if target_size:
        s = target_size / float(side)
        img = img.resize((max(1, int(w*s)), max(1, int(h*s))), Image.LANCZOS)
        w, h = img.size
        side = target_size

    canvas = Image.new(mode, (side, side), bg)
    x, y = (side - w)//2, (side - h)//2
    canvas.paste(img, (x, y), img if mode == "RGBA" else None)
    return canvas

# ================== 白底检测 ==================
def _is_white_bg(img: Image.Image) -> bool:
    """
    采样 8 个边缘区域（四角 + 四边中点），各占短边 WHITE_BG_PATCH 比例。
    任意一块平均 RGB 低于 255-WHITE_BG_TOL，则视为非白底，返回 False。
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = max(5, int(min(w, h) * WHITE_BG_PATCH))
    hx, hy = patch // 2, patch // 2
    regions = [
        (0,         0,         patch,     patch),
        (w - patch, 0,         w,         patch),
        (0,         h - patch, patch,     h),
        (w - patch, h - patch, w,         h),
        (w//2 - hx, 0,         w//2 + hx, patch),
        (w//2 - hx, h - patch, w//2 + hx, h),
        (0,         h//2 - hy, patch,     h//2 + hy),
        (w - patch, h//2 - hy, w,         h//2 + hy),
    ]
    threshold = 255 - WHITE_BG_TOL
    for box in regions:
        region = np.array(rgb.crop(box), dtype=float)
        if region.mean(axis=(0, 1)).min() < threshold:
            return False
    return True


# ================== 白毛边后处理 ==================
def _defringe_white(rgba: Image.Image) -> Image.Image:
    """
    去除白底抠图后的白毛边。

    原理：半透明边缘像素的颜色是"前景色 × alpha + 白色 × (1-alpha)"的混合结果。
    通过逆运算还原真实前景色：C_fg = (C_visible - (1-alpha) × 255) / alpha
    """
    arr = np.array(rgba, dtype=np.float32)
    a = arr[:, :, 3:4] / 255.0                  # alpha [0,1]
    mask = (a > 0) & (a < 1)                     # 仅处理半透明像素
    rgb = arr[:, :, :3]
    safe_a = np.where(mask, a, 1.0)              # 防除以0
    fg = (rgb - (1.0 - safe_a) * 255.0) / safe_a
    fg = np.clip(fg, 0, 255)
    arr[:, :, :3] = np.where(mask, fg, rgb)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def _erode_alpha(rgba: Image.Image, pixels: int = 1) -> Image.Image:
    """轻微侵蚀 alpha 通道，消除极边缘难以修复的半透明像素。"""
    if pixels <= 0:
        return rgba
    from PIL import ImageFilter
    r, g, b, a = rgba.split()
    for _ in range(pixels):
        a = a.filter(ImageFilter.MinFilter(3))
    return Image.merge("RGBA", (r, g, b, a))


def _close_alpha(rgba: Image.Image, radius: int = 5) -> Image.Image:
    """
    形态学闭运算：填充 alpha 通道内部的空洞（衣服底部/衣领被误抠成白色的修复）。

    原理：先膨胀 radius 次（MaxFilter），再腐蚀 radius 次（MinFilter）。
    效果：填补前景内的低 alpha 区域，而不会扩大外轮廓。
    """
    if radius <= 0:
        return rgba
    from PIL import ImageFilter
    r, g, b, a = rgba.split()
    for _ in range(radius):
        a = a.filter(ImageFilter.MaxFilter(3))
    for _ in range(radius):
        a = a.filter(ImageFilter.MinFilter(3))
    return Image.merge("RGBA", (r, g, b, a))


# ================== BRIA RMBG-2.0 本地抠图（免费最佳质量） ==================
_BRIA_MODEL = None
_BRIA_LOCK = threading.Lock()

def _get_bria_model():
    global _BRIA_MODEL
    if _BRIA_MODEL is None:
        with _BRIA_LOCK:
            if _BRIA_MODEL is None:
                print("⏳ 加载 BRIA RMBG-2.0 模型（首次会从 HuggingFace 下载约 200MB）...")
                try:
                    import torch
                    from transformers import AutoModelForImageSegmentation
                    model = AutoModelForImageSegmentation.from_pretrained(
                        "briaai/RMBG-2.0", trust_remote_code=True
                    )
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    model = model.to(device).eval()
                    _BRIA_MODEL = (model, device)
                    print(f"✅ BRIA RMBG-2.0 就绪（{device}）")
                except Exception as e:
                    print(f"❌ BRIA 模型加载失败：{e}")
                    raise
    return _BRIA_MODEL


def _cutout_via_bria(img: Image.Image) -> Image.Image:
    """
    使用 BRIA RMBG-2.0 本地抠图（免费，效果优于 birefnet）。
    需要：pip install transformers torch torchvision
    """
    import torch
    from torchvision import transforms

    model, device = _get_bria_model()
    orig_size = img.size

    transform = transforms.Compose([
        transforms.Resize((1024, 1024)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    rgb = img.convert("RGB")
    input_tensor = transform(rgb).unsqueeze(0).to(device)

    with torch.no_grad():
        preds = model(input_tensor)
    # 取最后一层输出，sigmoid 转概率，squeeze 到 (H, W)
    mask = preds[-1].sigmoid().squeeze().cpu()

    # 还原到原图尺寸
    mask_pil = transforms.ToPILImage()(mask).resize(orig_size, Image.LANCZOS)
    mask_arr = np.array(mask_pil)

    rgba = rgb.convert("RGBA")
    rgba_arr = np.array(rgba)
    rgba_arr[:, :, 3] = mask_arr
    result = Image.fromarray(rgba_arr, "RGBA")

    if ALPHA_CLOSING > 0:
        result = _close_alpha(result, ALPHA_CLOSING)
    if ALPHA_ERODE > 0:
        result = _erode_alpha(result, ALPHA_ERODE)
    if DEFRINGE_WHITE:
        result = _defringe_white(result)
    return result


# ================== remove.bg API 抠图 ==================
def _cutout_via_removebg(img: Image.Image) -> Image.Image:
    """
    调用 remove.bg API 抠图，返回 RGBA 图像。
    精度高于本地模型，对服装/复杂边缘尤其明显。
    API 文档：https://www.remove.bg/api
    """
    import requests
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)

    resp = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": ("image.png", buf, "image/png")},
        data={"size": REMOVEBG_SIZE},
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        timeout=60,
    )

    if resp.status_code == 200:
        result = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        # remove.bg 返回的已经是干净边缘，defringe 效果有限但无害
        if ALPHA_ERODE > 0:
            result = _erode_alpha(result, ALPHA_ERODE)
        if DEFRINGE_WHITE:
            result = _defringe_white(result)
        return result

    # API 失败：打印错误并回退到本地 rembg
    try:
        err = resp.json()
    except Exception:
        err = resp.text[:200]
    print(f"    ⚠️ remove.bg API 失败（{resp.status_code}）：{err}，回退到本地模型")
    return _cutout_via_rembg(img)


# ================== 本地 rembg 抠图（复用 session） ==================
from rembg import remove, new_session
_SESSION = None
_SESSION_LOCK = threading.Lock()

def _get_session():
    global _SESSION
    if _SESSION is None and AUTO_CUTOUT:
        with _SESSION_LOCK:
            if _SESSION is None:          # double-check inside lock
                print("⏳ 加载抠图模型（首次会下载模型文件）...")
                _SESSION = new_session(MODEL_NAME)
                print("✅ 模型就绪")
    return _SESSION

def _cutout_via_rembg(img: Image.Image) -> Image.Image:
    """使用本地 rembg 模型抠图，并做后处理去白毛边。"""
    sess = _get_session()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    cut = remove(
        buf.getvalue(),
        session=sess,
        alpha_matting=ALPHA_MATTING,
        alpha_matting_foreground_threshold=ALPHA_MATTING_FG_THRESHOLD,
        alpha_matting_background_threshold=ALPHA_MATTING_BG_THRESHOLD,
        alpha_matting_erode_size=ALPHA_MATTING_ERODE_SIZE,
    )
    result = Image.open(io.BytesIO(cut)).convert("RGBA")
    if ALPHA_CLOSING > 0:
        result = _close_alpha(result, ALPHA_CLOSING)
    if ALPHA_ERODE > 0:
        result = _erode_alpha(result, ALPHA_ERODE)
    if DEFRINGE_WHITE:
        result = _defringe_white(result)
    return result


def ensure_cutout(img: Image.Image) -> Image.Image:
    """
    抠图入口，按 CUTOUT_BACKEND 路由：
      "removebg" -> remove.bg API（需填 REMOVEBG_API_KEY，精度最高）
      "bria"     -> BRIA RMBG-2.0 本地模型（免费最佳，需装 transformers torch）
      "rembg"    -> 本地 rembg（默认，无额外依赖）

    白底图自动跳过（WHITE_BG_SKIP=True），已含透明通道直接返回。
    """
    if not AUTO_CUTOUT:
        return img
    # ① 白底检测
    if WHITE_BG_SKIP and _is_white_bg(img):
        print("    ⏩ 检测到白底，跳过抠图")
        return img
    # ② 已含有效透明通道
    rgba = img.convert("RGBA")
    amin, amax = rgba.split()[-1].getextrema()
    if amin < 255 and amax > 0:
        return rgba
    # ③ 按后端路由
    if CUTOUT_BACKEND == "removebg":
        print("    🌐 使用 remove.bg API 抠图...")
        return _cutout_via_removebg(img)
    elif CUTOUT_BACKEND == "bria":
        print("    🖥️  使用 BRIA RMBG-2.0 抠图...")
        return _cutout_via_bria(img)
    else:
        print(f"    🖥️  使用本地 rembg（{MODEL_NAME}）抠图...")
        return _cutout_via_rembg(img)


# ================== 水印（RGBA in/out） ==================
def add_diagonal_text_watermark(img: Image.Image) -> Image.Image:
    if not DIAGONAL_TEXT_ENABLE or not DIAGONAL_TEXT:
        return img
    base = img.convert("RGBA")
    w, h = base.size
    font = _get_font(max(16, int(w * DIAGONAL_FONT_SIZE_RATIO)))

    pad = int(max(w, h) * 0.25)
    tile_w, tile_h = w + pad * 2, h + pad * 2
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)

    text_w = draw.textlength(DIAGONAL_TEXT, font=font)
    step = max(10, int(w * DIAGONAL_STEP_RATIO))
    for y in range(0, tile_h, step):
        x = -tile_w
        while x < tile_w * 2:
            draw.text((x, y), DIAGONAL_TEXT, font=font, fill=(0, 0, 0, DIAGONAL_ALPHA))
            x += int(text_w * 1.5)

    tile = tile.rotate(DIAGONAL_ANGLE_DEG, expand=1, resample=Image.BICUBIC)
    tw, th = tile.size
    cx, cy = tw // 2, th // 2
    crop = tile.crop((cx - w // 2, cy - h // 2, cx - w // 2 + w, cy - h // 2 + h))
    return Image.alpha_composite(base, crop)

def add_local_logo(img: Image.Image, text: str = None) -> Image.Image:
    if not LOCAL_LOGO_ENABLE:
        return img
    txt = text or LOCAL_LOGO_TEXT or ""
    if not txt:
        return img
    base = img.convert("RGBA")
    w, h = base.size
    font = _get_font(max(14, int(w * LOCAL_FONT_SIZE_RATIO)))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        bbox = draw.textbbox((0, 0), txt, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = draw.textlength(txt, font=font), font.size
    margin = int(w * LOCAL_MARGIN_RATIO)
    x, y = w - tw - margin, h - th - margin
    draw.rectangle([x - margin // 2, y - margin // 4, x + tw + margin // 2, y + th + margin // 4],
                   fill=(255, 255, 255, LOCAL_BG_ALPHA))
    draw.text((x, y), txt, font=font, fill=(0, 0, 0, LOCAL_TEXT_ALPHA))
    return Image.alpha_composite(base, overlay)

# ================== 主流程 ==================
def process_one(path: Path, out_dir: Path, add_watermark: bool = True):
    try:
        print(f"  ▶ 载入：{path.name}")
        img = Image.open(str(path))

        # 1) 必要时抠图
        img = ensure_cutout(img)

        # 2) 精裁
        img = _autocrop_by_alpha(img, 5) if _has_alpha(img) else _autocrop_white_border(img, 8)

        # 3) 正方形居中（保持 RGBA 时不丢透明）
        img = _pad_to_square(img, TARGET_SIZE)

        # 4) 水印（RGBA in/out）
        if add_watermark:
            img = add_diagonal_text_watermark(img)
            img = add_local_logo(img, LOCAL_LOGO_TEXT)

        # 可选导出一份透明 PNG（方便后续复用）
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = path.stem
        if SAVE_TRANSPARENT_PNG and _has_alpha(img):
            png_out = out_dir / f"{stem}.png"
            img.save(str(png_out), optimize=True)
            print(f"    ✓ 透明PNG：{png_out.name}")

        # 5) 最终压到白底 -> JPG
        if _has_alpha(img):
            white = Image.new("RGB", img.size, CANVAS_COLOR)
            white.paste(img, (0, 0), img)
            final = white
        else:
            final = img.convert("RGB")

        jpg_out = out_dir / f"{stem}.jpg"
        final.save(str(jpg_out), quality=OUTPUT_JPEG_QUALITY, subsampling=0, optimize=True)
        print(f"    ✓ 输出JPG：{jpg_out.name}")
    except Exception as e:
        print(f"  ✗ 失败：{path.name} -> {e}")

def batch_process(input_dir: str, output_dir: str, max_workers: int = MAX_WORKERS, add_watermark: bool = True):
    in_dir, out_dir = Path(input_dir), Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 扫描目录：{in_dir.resolve()}")
    backend_info = {
        "removebg": f"remove.bg API（size={REMOVEBG_SIZE}）",
        "bria":     "BRIA RMBG-2.0（本地免费最佳）",
        "rembg":    f"rembg 本地（model={MODEL_NAME}）",
    }.get(CUTOUT_BACKEND, CUTOUT_BACKEND)
    print(f"🖼️  抠图后端：{backend_info}")

    groups = {}
    for p in in_dir.iterdir():
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            groups.setdefault(p.stem.lower(), []).append(p)

    # 同名优先 PNG
    files = []
    for _, lst in groups.items():
        lst.sort(key=lambda x: (x.suffix.lower() != ".png", x.name))
        files.append(lst[0])

    total = len(files)
    print(f"📊 待处理：{total} 张")
    if total == 0:
        print("⚠️ 未发现可处理的图片。")
        return

    t0 = time.time()
    if AUTO_CUTOUT and not REMOVEBG_API_KEY:
        _get_session()  # 提前加载本地模型

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_one, f, out_dir, add_watermark): f for f in files}
        for i, future in enumerate(as_completed(future_to_file), 1):
            f = future_to_file[future]
            try:
                future.result()
            except Exception as e:
                print(f"✗ 处理 {f.name} 出错：{e}")
            else:
                print(f"[{i}/{total}] {f.name} 完成")

    print(f"🎉 全部完成！总耗时 {time.time()-t0:.1f}s")


# ============== 直接运行 ==============
if __name__ == "__main__":
    batch_process(INPUT_DIR, OUTPUT_DIR)
