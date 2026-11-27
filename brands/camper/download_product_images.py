import io
import os
import requests
import time
from PIL import Image
from config import CAMPER
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置路径
input_file = CAMPER["LINKS_FILE"]
image_folder = CAMPER["IMAGE_DOWNLOAD"]

# Camper 图床（Scene7）同一商品有两套图：
#   _C/_F/_L/_T/_P        白底商品图，已贴边裁好（正面/斜侧/侧面/背面/鞋底），几乎每款都有 —— 主力
#   _CF/_DF/_FF/_LF/_SF/_TF 官网页面展示的灰底棚拍竖图（1024x1536）
# 灰底那套里 _DF（局部特写）/ _FF（倒影摆拍）在白底套里没有对应角度，作为第 6/7 张补充下载，
# 多数款式只有其中一张，没有就跳过。竖图直接补白边成方图会很突兀，所以下载时居中裁成正方形。
image_suffixes = ['_C.jpg', '_F.jpg', '_L.jpg', '_T.jpg', '_P.jpg']
extra_suffixes = ['_DF.jpg', '_FF.jpg']
base_url = "https://cloud.camper.com/is/image/YnJldW5pbmdlcjAx/"


def _center_square(content: bytes) -> bytes:
    """居中裁成正方形，返回 JPEG 字节。"""
    with Image.open(io.BytesIO(content)) as im:
        im = im.convert("RGB")
        w, h = im.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        buf = io.BytesIO()
        im.crop((left, top, left + side, top + side)).save(buf, format="JPEG", quality=95)
        return buf.getvalue()


# 下载函数（单张图片）
def download_image(code, suffix, idx, max_retries=3, delay=1.0, optional=False):
    image_url = base_url + code + suffix
    image_name = f"{code}{suffix}"
    save_path = os.path.join(image_folder, image_name)

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            # CDN 对不存在的图返回 200 + 空 text/html，不能当图片保存
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/') or not response.content:
                if os.path.exists(save_path):
                    os.remove(save_path)
                if optional:
                    return None   # 补充图大多数款式没有，不刷屏
                return f"⚠️ {idx:04d} - 无此图片: {image_name}（{content_type or '无类型'}, {len(response.content)} bytes）"
            content = _center_square(response.content) if optional else response.content
            with open(save_path, 'wb') as f:
                f.write(content)
            return f"✅ {idx:04d} - 下载成功: {image_name}{'（补充图，已裁成方图）' if optional else ''}"
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
            for suffix in extra_suffixes:
                tasks.append(executor.submit(download_image, code, suffix, idx, optional=True))

        for future in as_completed(tasks):
            msg = future.result()
            if msg:
                print(msg)

    print("🎯 所有图片多线程下载任务完成！")

if __name__ == "__main__":
    # 默认从 product_links.txt 下载
    download_camper_images()

    # 如果需要从指定文件下载，取消注释以下代码
    download_images_from_codes("D:/TB/camper_missing_codes.txt")
