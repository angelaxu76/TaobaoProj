# expand_square_add_code.py
# 供 pipeline 直接 import 调用：process_images(input_dir, output_dir, product_code, defend=True/False)

from __future__ import annotations
from pathlib import Path
import random
import re
import numpy as np
from typing import Iterable, List
from PIL import Image, ImageEnhance, ImageOps

# ===== 固定参数 =====
JPEG_QUALITY = 90
BG_RGB = (255, 255, 255)     # 方图白底
ROTATE_RANGE = (-1.2, 1.2)   # 旋转角度
CROP_PERCENT_RANGE = (0.4, 1.0)  # 轻裁剪百分比
BRIGHTNESS_JITTER = 0.03     # 亮度抖动
CONTRAST_JITTER = 0.03       # 对比度抖动
NOISE_OPACITY = 0.03         # 噪点透明度
BORDER_PADDING = 20          # 边框留白

# 支持的图片扩展（全部转小写后比较）
VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".jfif", ".avif", ".heic", ".heif")

# 可选：尝试注册 HEIF/HEIC 支持（若未安装 pillow-heif，不会报错）
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _iter_images(input_dir: Path) -> Iterable[Path]:
    """递归扫描 input_dir 下所有子目录的图片文件。"""
    files = []
    for p in input_dir.rglob("*"):
        if p.is_file():
            suf = p.suffix.lower()
            if suf in VALID_EXT and not p.name.startswith("."):
                files.append(p)
    files.sort(key=lambda x: _natural_key(x.name))
    print(f"▶ 共发现 {len(files)} 个图片文件（包含子目录）。根目录：{input_dir}")
    return files



def _to_square_canvas(im: Image.Image) -> Image.Image:
    """不缩放主体，铺成正方形白底"""
    w, h = im.size
    side = max(w, h)
    if im.mode in ("RGBA", "LA"):
        base = Image.new("RGB", im.size, BG_RGB)
        rgba = im.convert("RGBA")
        base.paste(rgba, mask=rgba.split()[-1])
        im = base
    elif im.mode != "RGB":
        im = im.convert("RGB")
    canvas = Image.new("RGB", (side, side), BG_RGB)
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas


def _safe_crop(img: Image.Image, percent: float) -> Image.Image:
    w, h = img.size
    dx = int(w * percent / 100.0)
    dy = int(h * percent / 100.0)
    dx = min(dx, w // 20)
    dy = min(dy, h // 20)
    return img.crop((dx, dy, w - dx, h - dy))


def _add_noise(img: Image.Image, opacity: float) -> Image.Image:
    """叠加半透明噪点"""
    w, h = img.size
    noise = np.random.randint(0, 50, (h, w, 3), dtype="uint8")
    layer = Image.fromarray(noise, "RGB").convert("RGBA")
    alpha = int(max(0.0, min(1.0, opacity)) * 255)
    layer.putalpha(alpha)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _defender_like(im: Image.Image) -> Image.Image:
    """扰动处理：加白边→旋转→裁剪→亮度/对比度→噪点"""
    im = ImageOps.expand(im.convert("RGB"), border=BORDER_PADDING, fill=BG_RGB)
    angle = random.uniform(*ROTATE_RANGE)
    im = im.rotate(angle, expand=True, fillcolor=BG_RGB)
    cp = random.uniform(*CROP_PERCENT_RANGE)
    im = _safe_crop(im, cp)
    im = ImageEnhance.Brightness(im).enhance(
        random.uniform(1 - BRIGHTNESS_JITTER, 1 + BRIGHTNESS_JITTER)
    )
    im = ImageEnhance.Contrast(im).enhance(
        random.uniform(1 - CONTRAST_JITTER, 1 + CONTRAST_JITTER)
    )
    im = _add_noise(im, opacity=NOISE_OPACITY)
    return im


def _save_jpeg(im: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(
        path,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
        subsampling=1,
    )


def process_images(
    input_dir: str | Path,
    output_dir: str | Path,
    product_code: str,
    defend: bool = True,
    watermark: bool = False,
    wm_text: str | None = None,        # 斜纹水印文字
    wm_logo_text: str | None = None,   # 右下角水印文字
) -> List[Path]:
    """
    处理目录下的所有图片，保存为 <output>/<product_code>/<product_code>_1.jpg 等
    defend=True 时加扰动，watermark=True 时加文字水印
    """
    input_dir = Path(input_dir)
    out_dir = Path(output_dir) / product_code
    out_dir.mkdir(parents=True, exist_ok=True)

    # === 延迟导入 text_watermark ===
    if watermark:
        tw = None
        try:
            from . import text_watermark as tw
        except Exception:
            try:
                from helper.image import add_text_watermark as tw
            except Exception:
                try:
                    import text_watermark as tw
                except Exception:
                    try:
                        import importlib.util
                        _p = Path(__file__).resolve().parent / "add_text_watermark.py"
                        if _p.exists():
                            spec = importlib.util.spec_from_file_location(
                                "text_watermark", str(_p)
                            )
                            tw = importlib.util.module_from_spec(spec)
                            assert spec.loader is not None
                            spec.loader.exec_module(tw)
                    except Exception:
                        tw = None

        if tw is None:
            print("⚠ 未能导入 text_watermark，将跳过水印。")
            watermark = False
        else:
            if wm_text is not None:
                tw.DIAGONAL_TEXT = wm_text
                tw.DIAGONAL_TEXT_ENABLE = True
            if wm_logo_text is not None:
                tw.LOCAL_LOGO_TEXT = wm_logo_text
                tw.LOCAL_LOGO_ENABLE = True
            if not getattr(tw, "DIAGONAL_TEXT_ENABLE", True) and not getattr(
                tw, "LOCAL_LOGO_ENABLE", True
            ):
                tw.DIAGONAL_TEXT_ENABLE = True

    outputs: List[Path] = []
    for idx, src in enumerate(_iter_images(input_dir), start=1):
        print(f"  - 处理: {src}")
        out_path = out_dir / f"{product_code}_{idx}.jpg"
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                if defend:
                    im = _defender_like(im)
                im = _to_square_canvas(im)

                if watermark:
                    if getattr(tw, "DIAGONAL_TEXT_ENABLE", True):
                        im = tw.add_diagonal_text_watermark(im)
                    if getattr(tw, "LOCAL_LOGO_ENABLE", True):
                        im = tw.add_local_logo(im)

                _save_jpeg(im, out_path)
            outputs.append(out_path)
        except Exception as e:
            print(f"⚠ 跳过 {src.name}: {e}")
    return outputs
