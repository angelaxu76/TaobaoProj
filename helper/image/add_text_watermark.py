# add_text_watermark.py —— 仅文字水印版本（斜纹 + 右下角）
from PIL import Image, ImageDraw, ImageFont
import math
import os

# ========= 全局配置（可按需修改） =========
DIAGONAL_TEXT_ENABLE = True
LOCAL_LOGO_ENABLE = True  # 这里表示“右下角文字”启用（不需要 logo 图）
DIAGONAL_TEXT = "英国哈梅尔百货"
LOCAL_LOGO_TEXT = "英国哈梅尔百货"

DIAGONAL_ALPHA = 30        # 0~255，斜纹文字透明度（数字越小越淡）
DIAGONAL_FONT_SIZE_RATIO = 0.02  # 文字大小 = 图宽 * 此比例
DIAGONAL_STEP_RATIO = 0.50       # 两行之间的间距 = 图宽 * 此比例
DIAGONAL_ANGLE_DEG =  -30        # 斜纹角度（-30° 更常见）

LOCAL_FONT_SIZE_RATIO = 0.04     # 右下角文字字号
LOCAL_MARGIN_RATIO = 0.03        # 距离右下边距
LOCAL_BG_ALPHA = 96              # 右下角背景透明度（0~255）
LOCAL_TEXT_ALPHA = 40           # 右下角文字透明度（0~255）

# 若你有自定义字体（中文更美观），把路径填到这里；否则自动用默认字体
FONT_PATH = None  # 例如 r"C:\Windows\Fonts\msyh.ttc"

def _get_font(px: int):
    try:
        if FONT_PATH:
            return ImageFont.truetype(FONT_PATH, px)
        # 兜底尝试中文字体/Arial
        for name in ["msyh.ttc", "simhei.ttf", "arial.ttf"]:
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                pass
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

def add_diagonal_text_watermark(img):
    """在整张图上铺“斜纹半透明文字”"""
    if not DIAGONAL_TEXT_ENABLE or not DIAGONAL_TEXT:
        return img

    w, h = img.size
    font_size = max(16, int(w * DIAGONAL_FONT_SIZE_RATIO))
    font = _get_font(font_size)

    # 文字尺寸（为计算行宽/高度）
    tmp_draw = ImageDraw.Draw(img)
    text_w, text_h = tmp_draw.textlength(DIAGONAL_TEXT, font=font), font.size

    # 创建透明叠加层
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 旋转坐标系思路：我们生成一张比原图略大的“文字平铺”层，旋转后再居中贴回
    pad = int(max(w, h) * 0.25)
    tile_w, tile_h = w + pad * 2, h + pad * 2
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tile)

    step = int(w * DIAGONAL_STEP_RATIO)  # 行距
    # 从左上到右下斜方向平铺
    for y in range(0, tile_h, step):
        # 水平向两侧填满（x 递增）
        x = -tile_w
        while x < tile_w * 2:
            tdraw.text((x, y), DIAGONAL_TEXT, font=font, fill=(0, 0, 0, DIAGONAL_ALPHA))
            x += int(text_w * 1.5)  # 相邻重复的水平距离

    # 旋转
    tile = tile.rotate(DIAGONAL_ANGLE_DEG, expand=1, resample=Image.BICUBIC)

    # 把旋转后的平铺层裁切成原图大小并贴回 overlay
    tw, th = tile.size
    cx, cy = tw // 2, th // 2
    left = cx - w // 2
    top = cy - h // 2
    tile_cropped = tile.crop((left, top, left + w, top + h))
    overlay = Image.alpha_composite(overlay, tile_cropped)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

def add_local_logo(img, text: str = None):
    """在右下角放一个带半透明底的文字块（不用 logo 图）"""
    if not LOCAL_LOGO_ENABLE:
        return img

    w, h = img.size
    text = text or LOCAL_LOGO_TEXT or ""
    if not text:
        return img

    font_size = max(14, int(w * LOCAL_FONT_SIZE_RATIO))
    font = _get_font(font_size)
    # 用 RGBA 叠加层绘制半透明背景 & 文字
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 文本尺寸
    # Pillow 新版推荐使用 textbbox 获得更准确的包围盒
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = draw.textlength(text, font=font), font.size

    margin = int(w * LOCAL_MARGIN_RATIO)
    x = w - tw - margin
    y = h - th - margin

    # 画半透明白底
    draw.rectangle([x - margin // 2, y - margin // 4, x + tw + margin // 2, y + th + margin // 4],
                   fill=(255, 255, 255, LOCAL_BG_ALPHA))
    # 画黑字
    draw.text((x, y), text, font=font, fill=(0, 0, 0, LOCAL_TEXT_ALPHA))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def pipeline_text_watermark(
    input_dir: str,
    output_dir: str,
    watermark_text: str | None = None,
) -> None:
    """
    批量处理目录中的图片，加水印后保存到指定目录

    watermark_text:
        如果不为 None，则在这里覆盖全局水印文字：
        - DIAGONAL_TEXT（斜纹水印）
        - LOCAL_LOGO_TEXT（右下角文字）
    """
    global DIAGONAL_TEXT, LOCAL_LOGO_TEXT

    # 如果调用时传入了水印文字，就覆盖全局配置
    if watermark_text:
        DIAGONAL_TEXT = watermark_text
        LOCAL_LOGO_TEXT = watermark_text

    os.makedirs(output_dir, exist_ok=True)
    exts = {".jpg", ".jpeg", ".png"}

    for fname in os.listdir(input_dir):
        fpath = os.path.join(input_dir, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in exts:
            continue

        try:
            img = Image.open(fpath).convert("RGB")
            img = add_diagonal_text_watermark(img)
            img = add_local_logo(img)

            out_path = os.path.join(output_dir, fname)
            img.save(out_path, quality=95)
            print(f"✅ 处理完成: {fname} -> {out_path}")
        except Exception as e:
            print(f"❌ 处理失败: {fname}, 错误: {e}")
