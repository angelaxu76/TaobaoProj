import argparse
import shutil
from PIL import Image, ImageChops
from pathlib import Path

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

def copy_images(src_dir: Path, dst_dir: Path):
    # 检查目标目录是否存在，不存在则创建
    dst_dir.mkdir(parents=True, exist_ok=True)

    # 支持的图片扩展名
    image_extensions = {".jpg", ".jpeg", ".png"}

    count = 0
    for file in src_dir.glob("*"):
        if file.suffix.lower() in image_extensions:
            target_file = dst_dir / file.name
            shutil.copyfile(file, target_file)
            count += 1
            print(f"✅ 复制: {file.name}")

    print(f"\n🎉 完成，共复制 {count} 张图片")

def expand_to_square(image: Image.Image, bg_color=(240, 240, 240)) -> Image.Image:
    width, height = image.size
    max_dim = max(width, height)
    square_bg = Image.new("RGB", (max_dim, max_dim), bg_color)
    offset = ((max_dim - width) // 2, (max_dim - height) // 2)
    square_bg.paste(image, offset)
    return square_bg

def run_crop_and_expand(input_dir: Path, output_dir: Path, bg_color, tolerance, quality):
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for img_path in input_dir.glob(ext):
            try:
                with Image.open(img_path) as img:
                    cropped = crop_gray_border(img, bg_color=bg_color, tolerance=tolerance)
                    square = expand_to_square(cropped, bg_color=bg_color)

                    output_name = img_path.stem + ".jpg"
                    output_path = output_dir / output_name
                    square.save(output_path, format="JPEG", quality=quality, optimize=True, progressive=True)

                    print(f"✅ 已裁剪+填充: {output_name}")
                    count += 1
            except Exception as e:
                print(f"❌ 出错: {img_path.name} - {e}")
    print(f"\n🎉 所有图片处理完毕，共处理 {count} 张。")

def parse_rgb(color_str):
    try:
        parts = [int(c) for c in color_str.split(",")]
        if len(parts) != 3:
            raise ValueError
        return tuple(parts)
    except:
        raise argparse.ArgumentTypeError("背景色格式必须是 R,G,B 形式，例如 240,240,240")

def main():
    parser = argparse.ArgumentParser(description="裁剪灰边并扩展为方图（支持任意品牌）")
    parser.add_argument("--input", required=True, help="输入图片文件夹路径")
    parser.add_argument("--output", required=True, help="输出图片文件夹路径")
    parser.add_argument("--bg_color", type=parse_rgb, default="240,240,240", help="背景色RGB，默认 240,240,240")
    parser.add_argument("--tolerance", type=int, default=35, help="灰边容差，默认 35")
    parser.add_argument("--quality", type=int, default=80, help="JPEG压缩质量（1-100），默认80")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    run_crop_and_expand(input_dir, output_dir, args.bg_color, args.tolerance, args.quality)

if __name__ == "__main__":
    main()
