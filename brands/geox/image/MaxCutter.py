from PIL import Image, ImageChops
from pathlib import Path

# === 配置参数 ===
INPUT_DIR = Path(r"D:\TB\Products\geox\document\images_def")
OUTPUT_DIR = Path(r"D:\TB\Products\geox\document\images")
BG_COLOR = (240, 240, 240)
TOLERANCE = 35
OUTPUT_QUALITY = 80  # 输出图片压缩质量（1-100）

# === 创建输出目录 ===
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 裁剪灰边 ===
def crop_gray_border(image: Image.Image, bg_color=(240, 240, 240), tolerance=35) -> Image.Image:
    def get_bbox(img, ref_color, tol):
        bg = Image.new("RGB", img.size, ref_color)
        diff = ImageChops.difference(img, bg).convert("L")
        mask = diff.point(lambda x: 0 if x <= tol else 255)
        return mask.getbbox()

    image = image.convert("RGB")
    bbox1 = get_bbox(image, bg_color, tolerance)
    cropped = image.crop(bbox1) if bbox1 else image

    # 再次尝试收缩右下角残留灰边
    bbox2 = get_bbox(cropped, bg_color, tolerance)
    if bbox2:
        left, top, right, bottom = bbox2
        cropped = cropped.crop((0, 0, right, bottom))

    return cropped

# === 扩展成正方形 ===
def expand_to_square(image: Image.Image, bg_color=(240, 240, 240)) -> Image.Image:
    width, height = image.size
    max_dim = max(width, height)
    square_bg = Image.new("RGB", (max_dim, max_dim), bg_color)
    offset = ((max_dim - width) // 2, (max_dim - height) // 2)
    square_bg.paste(image, offset)
    return square_bg

# === 主处理函数 ===
def run_crop_and_expand():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for img_path in INPUT_DIR.glob(ext):
            try:
                with Image.open(img_path) as img:
                    cropped = crop_gray_border(img, bg_color=BG_COLOR, tolerance=TOLERANCE)
                    square = expand_to_square(cropped, bg_color=BG_COLOR)

                    # 输出统一为 .jpg 格式
                    output_name = img_path.stem + ".jpg"
                    output_path = OUTPUT_DIR / output_name
                    square.save(output_path, format="JPEG", quality=OUTPUT_QUALITY, optimize=True, progressive=True)

                    print(f"✅ 已裁剪+填充并压缩: {output_name}")
                    count += 1
            except Exception as e:
                print(f"❌ 出错: {img_path.name} - {e}")
    print(f"🎉 所有图片处理完毕，共处理 {count} 张。")

def main():
    run_crop_and_expand()

# === 运行入口 ===
if __name__ == "__main__":
    main()
