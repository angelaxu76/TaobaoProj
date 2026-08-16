# watermark_batch_cli.py —— 文字水印批量处理工具（直接改下面配置区后运行即可）
#
# 用法：改好下方 CONFIG 区域的参数，直接运行本文件（IDE 里点 Run 或 python watermark_batch_cli.py）

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ========================= CONFIG（直接改这里） =========================

INPUT_DIR = r"D:\TB\Products\barbour\document\barbour_size_avg_cutter"           # 输入目录
OUTPUT_DIR = r"D:\TB\Products\barbour\document\barbour_size_avg_cutter_watermarked"         # 输出目录
WATERMARK_TEXT = "英国玛莎百货商店"      # 水印文字

FONT_PATH = None                    # 自定义字体路径，如 r"C:\Windows\Fonts\msyh.ttc"；None 则自动尝试系统中文字体
FONT_SIZE = None                    # 固定字号（像素）。留 None 则按图片宽度 * FONT_SIZE_RATIO 自动计算
FONT_SIZE_RATIO = 0.05              # 字号 = 图宽 * 此比例（FONT_SIZE 为 None 时生效）

COLOR = (210, 230, 242)             # 水印颜色 (R, G, B)
OPACITY = 128                       # 水印深浅，0~255，越小越淡

MODE = "tile"                       # "tile"=整图斜纹平铺（防盗图效果好） / "corner"=单个角落 / "center"=居中单个
ANGLE = -30                         # 旋转角度（tile / center 模式生效）
POSITION = "bottom-right"           # mode="corner" 时的位置：top-left / top-right / bottom-left / bottom-right
TILE_SPACING_RATIO = 3.0            # tile 模式下文字间距倍数，越大越稀疏
CORNER_MARGIN_RATIO = 0.03          # corner 模式下距边距离，占图片短边的比例

# ========================================================================

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_FONT_CANDIDATES = ["msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf"]


def get_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    for name in DEFAULT_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_tile_watermark(
    img: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    opacity: int,
    angle: float,
    spacing_ratio: float,
) -> Image.Image:
    w, h = img.size
    tmp_draw = ImageDraw.Draw(img)
    text_w, text_h = text_size(tmp_draw, text, font)

    pad = int(max(w, h) * 0.3)
    tile_w, tile_h = w + pad * 2, h + pad * 2
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tile)

    step_x = int(text_w * spacing_ratio) or 1
    step_y = int(text_h * spacing_ratio * 3) or 1
    # 保证不管字号多大，平铺层里始终有足够多行/列，避免旋转裁切后水印刚好落在可视区域之外
    step_x = min(step_x, max(1, tile_w // 4))
    step_y = min(step_y, max(1, tile_h // 6))
    fill = (*color, opacity)

    y = 0
    while y < tile_h:
        x = 0
        while x < tile_w:
            tdraw.text((x, y), text, font=font, fill=fill)
            x += step_x
        y += step_y

    tile = tile.rotate(angle, expand=1, resample=Image.BICUBIC)
    tw, th = tile.size
    left = tw // 2 - w // 2
    top = th // 2 - h // 2
    tile_cropped = tile.crop((left, top, left + w, top + h))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    overlay = Image.alpha_composite(overlay, tile_cropped)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_single_watermark(
    img: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    opacity: int,
    angle: float,
    position: str,
    margin_ratio: float,
) -> Image.Image:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    text_w, text_h = text_size(draw, text, font)

    # 先在独立画布上画好文字再旋转，避免旋转裁切影响定位
    text_layer = Image.new("RGBA", (text_w + 20, text_h + 20), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(text_layer)
    tdraw.text((10, 10), text, font=font, fill=(*color, opacity))
    if angle:
        text_layer = text_layer.rotate(angle, expand=True, resample=Image.BICUBIC)

    tw, th = text_layer.size
    margin = int(min(w, h) * margin_ratio)

    if position == "center":
        x, y = (w - tw) // 2, (h - th) // 2
    elif position == "top-left":
        x, y = margin, margin
    elif position == "top-right":
        x, y = w - tw - margin, margin
    elif position == "bottom-left":
        x, y = margin, h - th - margin
    else:  # bottom-right
        x, y = w - tw - margin, h - th - margin

    overlay.paste(text_layer, (x, y), text_layer)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def process_image(fpath: Path, out_path: Path) -> None:
    img = Image.open(fpath).convert("RGB")
    w, _ = img.size
    size = FONT_SIZE if FONT_SIZE else max(12, int(w * FONT_SIZE_RATIO))
    font = get_font(FONT_PATH, size)

    if MODE == "tile":
        result = draw_tile_watermark(img, WATERMARK_TEXT, font, COLOR, OPACITY, ANGLE, TILE_SPACING_RATIO)
    else:
        use_angle = ANGLE if MODE == "center" else 0
        result = draw_single_watermark(img, WATERMARK_TEXT, font, COLOR, OPACITY, use_angle, POSITION, CORNER_MARGIN_RATIO)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {"quality": 95} if out_path.suffix.lower() in (".jpg", ".jpeg") else {}
    result.save(out_path, **save_kwargs)


def batch_watermark() -> None:
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not files:
        print(f"[WARN] 未在 {INPUT_DIR} 找到支持的图片文件（{', '.join(SUPPORTED_EXTS)}）")
        return

    for fpath in files:
        out_path = out_dir / fpath.name
        try:
            process_image(fpath, out_path)
            print(f"[OK] {fpath.name} -> {out_path}")
        except Exception as e:
            print(f"[FAIL] {fpath.name} 处理失败: {e}")


if __name__ == "__main__":
    batch_watermark()
