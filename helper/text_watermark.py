# -*- coding: utf-8 -*-
"""
批量给模特图打“低干扰+难去除”的水印：
1) 半透明斜线文字水印（全图覆盖）
2) 右下角局部 LOGO/店铺名水印（自动描边以防丢失）
3) 写入版权/来源到 EXIF/PNG 文本

使用：
  1) 修改下面“参数区”的路径和开关
  2) 运行：python watermark_batch.py

支持：JPG/PNG/WebP/TIFF/BMP
"""

from pathlib import Path
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin
import math
import piexif  # 可选：写入JPEG EXIF；如未安装，设 EXIF_WRITE=False 即可跳过

# ========== 参数区 ==========
INPUT_DIR   = Path(r"D:\TEMP1\image")       # 输入目录
OUTPUT_DIR  = Path(r"D:\TEMP1\imagewater")      # 输出目录
RECURSIVE   = True                      # 是否递归子目录
OVERWRITE   = True                      # 是否覆盖同名文件
SUFFIX      = "_wm"                     # 输出文件名后缀（保留原扩展名）

# --- 斜线文字水印 ---
DIAGONAL_TEXT_ENABLE   = True
DIAGONAL_TEXT          = "英国哈梅尔百货"  # 你的店铺/品牌名
FONT_PATH              = r"C:\Windows\Fonts\msyh.ttc"  # 字体路径；找不到会自动降级
FONT_SIZE_RATIO        = 0.045          # 文字相对短边的比例（0.03~0.06）
DIAGONAL_ALPHA         = 0.05           # 透明度（0~1，建议 0.10~0.15）
DIAGONAL_ANGLE_DEG     = 30             # 旋转角度（正斜线）
DIAGONAL_GAP_RATIO     = 0.35           # 相邻水印间距，相对文字长度（0.22~0.35）

# --- 局部LOGO/店铺名 ---
LOCAL_LOGO_ENABLE      = True
LOCAL_LOGO_IMAGE       = None           # e.g. r"D:\logo.png"；为 None 则用文字
LOCAL_LOGO_TEXT        = "英国哈梅尔百货"   # 当没有LOGO图片时使用
LOCAL_LOGO_OPACITY     = 0.35           # 局部水印不那么透明（便于识别）
LOCAL_LOGO_SCALE       = 0.18           # LOGO宽度占图短边的比例（0.12~0.22）
LOCAL_MARGIN_RATIO     = 0.035          # 边距占短边比例
LOCAL_STROKE           = True           # 文字描边
LOCAL_STROKE_WIDTH     = 2

# --- 版权信息写入 ---
EXIF_WRITE             = True           # 需要 pip install piexif
COPYRIGHT_TEXT         = "© AXX Supplier | Do not copy"

# ========== 工具函数 ==========
def load_font(fallback_size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, fallback_size)
    except Exception:
        return ImageFont.load_default()

def add_diagonal_text_watermark(im: Image.Image) -> Image.Image:
    w, h = im.size
    short = min(w, h)
    font_size = max(14, int(short * FONT_SIZE_RATIO))
    font = load_font(font_size)

    # 在透明层上绘制水印
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # 先做一条基准水印，测量宽高
    text = DIAGONAL_TEXT
    tw, th = draw.textbbox((0, 0), text, font=font)[2:]
    # 设置间距：横向/纵向都用文字宽度的一个倍数
    gap = max(8, int(tw * DIAGONAL_GAP_RATIO))

    # 旋转大画布思路：先在“加长画布”上铺，再旋转，最后贴回
    big = Image.new("RGBA", (int(w * 1.5 + tw), int(h * 1.5 + th)), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(big)

    # 以平行四边形方式平铺
    step_x = tw + gap
    step_y = th + gap
    for y in range(0, big.size[1] + step_y, step_y):
        # 错位排列视觉更自然
        offset = (y // step_y) % 2 * (step_x // 2)
        for x in range(-step_x, big.size[0] + step_x, step_x):
            bdraw.text((x + offset, y),
                       text,
                       fill=(255, 255, 255, int(255 * DIAGONAL_ALPHA)),
                       font=font)

    rot = big.rotate(DIAGONAL_ANGLE_DEG, expand=True, resample=Image.BICUBIC)
    # 居中裁回原尺寸
    cx, cy = rot.size[0] // 2, rot.size[1] // 2
    box = (cx - w // 2, cy - h // 2, cx - w // 2 + w, cy - h // 2 + h)
    rot_cropped = rot.crop(box)

    out = Image.alpha_composite(im.convert("RGBA"), rot_cropped)
    return out.convert("RGB")

def add_local_logo(im: Image.Image) -> Image.Image:
    w, h = im.size
    short = min(w, h)
    margin = int(short * LOCAL_MARGIN_RATIO)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    if LOCAL_LOGO_IMAGE:
        # 贴图LOGO
        logo = Image.open(LOCAL_LOGO_IMAGE).convert("RGBA")
        target_w = int(short * LOCAL_LOGO_SCALE)
        scale = target_w / max(1, logo.size[0])
        logo = logo.resize((target_w, int(logo.size[1] * scale)), Image.LANCZOS)

        # 设定位置：右下角黄金分割点稍上（避免遮挡下边缘）
        x = w - logo.size[0] - margin
        y = h - logo.size[1] - margin
        # 调整透明度
        if LOCAL_LOGO_OPACITY < 1:
            alpha = logo.split()[-1].point(lambda a: int(a * LOCAL_LOGO_OPACITY))
            logo.putalpha(alpha)

        layer.paste(logo, (x, y), logo)
    else:
        # 用文字LOGO
        font_size = max(16, int(short * LOCAL_LOGO_SCALE * 0.38))
        font = load_font(font_size)
        text = LOCAL_LOGO_TEXT

        tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        x = w - tw - margin
        y = h - th - margin

        # 自动选择前景：白色并加描边（黑）以适配深浅背景
        fill = (255, 255, 255, int(255 * LOCAL_LOGO_OPACITY))
        if LOCAL_STROKE:
            draw.text((x, y), text, font=font,
                      fill=fill, stroke_width=LOCAL_STROKE_WIDTH, stroke_fill=(0, 0, 0, int(255 * LOCAL_LOGO_OPACITY)))
        else:
            draw.text((x, y), text, font=font, fill=fill)

    out = Image.alpha_composite(im.convert("RGBA"), layer)
    return out.convert("RGB")

def write_metadata_jpeg(fp: Path, comment: str):
    try:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif_dict["0th"][piexif.ImageIFD.Artist] = comment
        exif_dict["0th"][piexif.ImageIFD.Copyright] = comment
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(fp))
    except Exception:
        pass  # 忽略元数据失败

def save_with_metadata(im: Image.Image, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        im.save(out_path, quality=92, subsampling=1)
        if EXIF_WRITE:
            write_metadata_jpeg(out_path, COPYRIGHT_TEXT)
    elif ext in [".png"]:
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Copyright", COPYRIGHT_TEXT)
        im.save(out_path, pnginfo=meta, optimize=True)
    else:
        im.save(out_path)

def process_one(img_path: Path, out_path: Path):
    try:
        with Image.open(img_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")

            if DIAGONAL_TEXT_ENABLE:
                im = add_diagonal_text_watermark(im)
            if LOCAL_LOGO_ENABLE:
                im = add_local_logo(im)

            save_with_metadata(im, out_path)
        print(f"✅ {img_path.name} -> {out_path.name}")
    except Exception as e:
        print(f"❌ {img_path}: {e}")

def valid_img(p: Path) -> bool:
    return p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"]

def main():
    files = []
    if RECURSIVE:
        files = [p for p in INPUT_DIR.rglob("*") if p.is_file() and valid_img(p)]
    else:
        files = [p for p in INPUT_DIR.iterdir() if p.is_file() and valid_img(p)]

    if not files:
        print("（未找到图片）")
        return

    print(f"共 {len(files)} 张，开始打水印…")
    for p in files:
        rel = p.relative_to(INPUT_DIR)
        out = (OUTPUT_DIR / rel.parent / (p.stem + SUFFIX + p.suffix))
        if (not OVERWRITE) and out.exists():
            print(f"跳过（已存在）：{out}")
            continue
        process_one(p, out)

if __name__ == "__main__":
    # 如果不需要EXIF写入，可将顶部 EXIF_WRITE=False，同时不安装 piexif
    try:
        import piexif  # noqa: F401
    except Exception:
        if EXIF_WRITE:
            print("提示：未安装 `piexif`，将跳过JPEG EXIF写入。可安装：pip install piexif")
            globals()['EXIF_WRITE'] = False
    main()
