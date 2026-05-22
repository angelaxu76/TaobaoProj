from PIL import Image
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import time

# === 配置项 ===
IMAGE_DIR = Path(r"D:\TB\Products\marksandspencer\publication\linkfox_output_1")
MAX_WIDTH = 1500

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}


def ensure_jpg(image_path: Path) -> Path:
    if image_path.suffix.lower() in (".jpg", ".jpeg"):
        return image_path
    jpg_path = image_path.with_suffix(".jpg")
    with Image.open(image_path) as img:
        img.convert("RGB").save(jpg_path, format="JPEG", quality=95, optimize=True)
    image_path.unlink()
    return jpg_path, True  # (新路径, 发生了格式转换)


def resize_image(image_path: Path) -> dict:
    """返回处理结果 dict，供主进程汇总日志。"""
    t0 = time.perf_counter()
    converted = False
    try:
        result = ensure_jpg(image_path)
        if isinstance(result, tuple):
            image_path, converted = result
        else:
            image_path = result

        with Image.open(image_path) as img:
            orig_w, orig_h = img.size
            if orig_w <= MAX_WIDTH:
                elapsed = time.perf_counter() - t0
                return {"name": image_path.name, "action": "skip", "converted": converted,
                        "orig_size": (orig_w, orig_h), "elapsed": elapsed}

            new_h = int(orig_h * MAX_WIDTH / orig_w)
            resized = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
            if resized.mode != "RGB":
                resized = resized.convert("RGB")
            resized.save(image_path, format="JPEG", quality=95, optimize=True)

        elapsed = time.perf_counter() - t0
        return {"name": image_path.name, "action": "resized", "converted": converted,
                "orig_size": (orig_w, orig_h), "new_size": (MAX_WIDTH, new_h), "elapsed": elapsed}

    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {"name": image_path.name, "action": "error", "error": str(e), "elapsed": elapsed}


def batch_resize_images(directory: Path):
    files = [f for f in sorted(directory.glob("*")) if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    total = len(files)
    if total == 0:
        print("目录中没有找到支持的图片文件。")
        return

    print(f"共找到 {total} 张图片，开始处理...\n")
    t_start = time.perf_counter()

    resized_count = skipped_count = error_count = converted_count = 0
    done = 0

    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(resize_image, f): f for f in files}
        for future in as_completed(futures):
            done += 1
            r = future.result()
            elapsed = r["elapsed"]

            if r["action"] == "resized":
                resized_count += 1
                conv_tag = " [格式转换]" if r["converted"] else ""
                print(f"  [{done:>3}/{total}] 压缩{conv_tag}  {r['name']}  "
                      f"{r['orig_size'][0]}x{r['orig_size'][1]} -> {r['new_size'][0]}x{r['new_size'][1]}  "
                      f"({elapsed:.2f}s)")
            elif r["action"] == "skip":
                skipped_count += 1
                conv_tag = " [格式转换]" if r["converted"] else ""
                print(f"  [{done:>3}/{total}] 跳过{conv_tag}   {r['name']}  "
                      f"{r['orig_size'][0]}x{r['orig_size'][1]} 无需缩放  ({elapsed:.2f}s)")
            else:
                error_count += 1
                print(f"  [{done:>3}/{total}] 失败    {r['name']}  错误: {r['error']}")

            if r.get("converted"):
                converted_count += 1

    total_elapsed = time.perf_counter() - t_start
    speed = total / total_elapsed if total_elapsed > 0 else 0

    print(f"""
{'='*55}
处理完成
  总计:    {total} 张
  压缩:    {resized_count} 张
  跳过:    {skipped_count} 张（宽度已 <= {MAX_WIDTH}px）
  格式转换: {converted_count} 张（非 JPG -> JPG）
  失败:    {error_count} 张
  总耗时:  {total_elapsed:.1f}s  |  平均速度: {speed:.1f} 张/s
{'='*55}""")


if __name__ == "__main__":
    batch_resize_images(IMAGE_DIR)
