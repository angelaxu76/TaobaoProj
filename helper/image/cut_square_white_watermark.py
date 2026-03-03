# -*- coding: utf-8 -*-
"""
cut_square_white_watermark.py  —  透明保留到最后一步，再压白底转 JPG
流程：
  1) 必要时自动抠图（rembg，可关）
  2) 按 alpha 或白边精裁
  3) 正方形居中：有透明→RGBA透明画布；无透明→RGB白底
  4) 水印：全程 RGBA 合成，不丢透明
  5) 最终一次性压到白底 → 保存 JPG（可选同步保存透明 PNG）
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
MODEL_NAME = "birefnet-general"        # 推荐: birefnet-general(最佳) > isnet-general-use > u2net

# 白底检测（跳过已是白底的图）
WHITE_BG_SKIP  = True    # True=检测到白底就跳过抠图；False=全部强制抠图
WHITE_BG_TOL   = 15      # 255-tol 以上算白色（越小越严格）
WHITE_BG_PATCH = 0.04    # 角落采样区域占短边的比例

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
# （birefnet 单次推理吃满 CPU，线程过多反而更慢）
MAX_WORKERS = 7

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
    正方形居中：有透明→RGBA透明画布；无透明→RGB白底。
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

    四角采样能识别均匀白底；四边中点采样能识别"角落是白但内部是灰"的情况
    （常见于带白框的灰色摄影棚背景图）。
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = max(5, int(min(w, h) * WHITE_BG_PATCH))
    hx, hy = patch // 2, patch // 2          # 中点采样区半宽/半高
    regions = [
        # 四个角落
        (0,         0,         patch,     patch),
        (w - patch, 0,         w,         patch),
        (0,         h - patch, patch,     h),
        (w - patch, h - patch, w,         h),
        # 四边中点
        (w//2 - hx, 0,         w//2 + hx, patch),      # 上中
        (w//2 - hx, h - patch, w//2 + hx, h),          # 下中
        (0,         h//2 - hy, patch,     h//2 + hy),  # 左中
        (w - patch, h//2 - hy, w,         h//2 + hy),  # 右中
    ]
    threshold = 255 - WHITE_BG_TOL
    for box in regions:
        region = np.array(rgb.crop(box), dtype=float)
        if region.mean(axis=(0, 1)).min() < threshold:
            return False
    return True


# ================== 自动抠图（复用 session） ==================
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

def ensure_cutout(img: Image.Image) -> Image.Image:
    """
    白底图 → 跳过（WHITE_BG_SKIP=True 时）；
    已含透明通道 → 直接返回；
    其余 → 调用 rembg 抠图。
    """
    if not AUTO_CUTOUT:
        return img
    # ① 白底检测：白底图跳过抠图
    if WHITE_BG_SKIP and _is_white_bg(img):
        print("    ⏩ 检测到白底，跳过抠图")
        return img
    # ② 已含有效透明通道 → 直接复用
    rgba = img.convert("RGBA")
    amin, amax = rgba.split()[-1].getextrema()
    if amin < 255 and amax > 0:
        return rgba
    # ③ 调用 rembg 抠图
    sess = _get_session()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    cut = remove(buf.getvalue(), session=sess)
    return Image.open(io.BytesIO(cut)).convert("RGBA")

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
    # 裁回画面并叠加
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
    # 半透明白底 + 文本
    draw.rectangle([x - margin // 2, y - margin // 4, x + tw + margin // 2, y + th + margin // 4],
                   fill=(255, 255, 255, LOCAL_BG_ALPHA))
    draw.text((x, y), txt, font=font, fill=(0, 0, 0, LOCAL_TEXT_ALPHA))
    return Image.alpha_composite(base, overlay)

# ================== 主流程 ==================
def process_one(path: Path, out_dir: Path):
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
        img = add_diagonal_text_watermark(img)
        img = add_local_logo(img, LOCAL_LOGO_TEXT)

        # 可选导出一份透明 PNG（方便后续复用）
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = path.stem
        if SAVE_TRANSPARENT_PNG and _has_alpha(img):
            png_out = out_dir / f"{stem}.png"
            img.save(str(png_out), optimize=True)
            print(f"    ✓ 透明PNG：{png_out.name}")

        # 5) 最终压到白底 → JPG
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

def batch_process(input_dir: str, output_dir: str, max_workers: int = MAX_WORKERS):
    in_dir, out_dir = Path(input_dir), Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 扫描目录：{in_dir.resolve()}")
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
    if AUTO_CUTOUT:
        _get_session()  # 提前加载一次模型，避免每线程重复加载

    # 多线程执行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_one, f, out_dir): f for f in files}
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
