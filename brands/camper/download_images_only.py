import os
import requests
import time
from config import CAMPER
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置路径
input_file = CAMPER["LINKS_FILE"]
image_folder = CAMPER["IMAGE_DOWNLOAD"]
image_suffixes = ['_C.jpg', '_F.jpg', '_L.jpg', '_T.jpg', '_P.jpg']
base_url = "https://cloud.camper.com/is/image/YnJldW5pbmdlcjAx/"

# 下载函数（单张图片）
def download_image(code, suffix, idx, max_retries=3, delay=1.0):
    image_url = base_url + code + suffix
    image_name = f"{code}{suffix}"
    save_path = os.path.join(image_folder, image_name)

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return f"✅ {idx:04d} - 下载成功: {image_name}"
        except Exception as e:
            if attempt < max_retries:
                time.sleep(delay)
            else:
                return f"❌ {idx:04d} - 下载失败: {image_name}，原因: {e}"

# 从 URL 文件中下载
def download_camper_images(max_workers: int = 10):
    os.makedirs(image_folder, exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    codes = []
    for url in urls:
        parts = url.split('-')
        if len(parts) >= 2:
            code = parts[-2] + '-' + parts[-1]
            codes.append(code)

    print(f"📦 共 {len(codes)} 个编码，开始多线程下载图片...")
    _download_images(codes, max_workers)

# 从编码文件中下载（新增方法）
def download_images_from_codes(codes_file: str, max_workers: int = 10):
    os.makedirs(image_folder, exist_ok=True)

    with open(codes_file, 'r', encoding='utf-8') as f:
        codes = [line.strip() for line in f if line.strip()]

    print(f"📦 从文件中读取 {len(codes)} 个编码，开始多线程下载图片...")
    _download_images(codes, max_workers)

# 通用下载方法
def _download_images(codes, max_workers):
    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, code in enumerate(codes, 1):
            for suffix in image_suffixes:
                tasks.append(executor.submit(download_image, code, suffix, idx))

        for future in as_completed(tasks):
            print(future.result())

    print("🎯 所有图片多线程下载任务完成！")

if __name__ == "__main__":
    # 默认从 product_links.txt 下载
    download_camper_images()

    # 如果需要从指定文件下载，取消注释以下代码
    # download_images_from_codes("D:/TB/camper_missing_codes.txt")
