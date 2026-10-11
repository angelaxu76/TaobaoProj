import re
import json
import threading
import psycopg2
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CLARKS, ensure_all_dirs
from psycopg2.extras import RealDictCursor
from brands.clarks.helpers_local import http_fetch

# === 配置 ===
PRODUCT_LINKS_FILE = CLARKS["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = CLARKS["IMAGE_DOWNLOAD"]
# 页面抓取走 http_fetch（被 403 后自动切 Selenium）；Selenium driver 不是线程安全的，需加锁
_page_lock = threading.Lock()
MAX_WORKERS = 5
SKIP_EXISTING_IMAGE = True

ensure_all_dirs(IMAGE_DIR)




def extract_product_code(url):
    match = re.search(r'/([0-9]+)-p', url)
    return match.group(1) if match else "unknown"


def extract_image_urls(soup):
    image_urls = []
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag:
        try:
            json_data = json.loads(script_tag.string)
            image_urls = json_data.get("props", {}).get("pageProps", {}).get("product", {}).get("imageUrls", [])
        except Exception as e:
            print(f"⚠️ 图片 JSON 提取失败: {e}")
    return image_urls


def download_image(url, save_path):
    try:
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 已存在，跳过: {save_path.name}")
            return
        r = http_fetch._session.get(url, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            print(f"🖼️ 下载成功: {save_path.name}")
        else:
            print(f"⚠️ 图片请求失败（{r.status_code}）: {url}")
    except Exception as e:
        print(f"❌ 下载失败: {url} → {e}")


def process_image_only(url):
    print(f"📷 处理图片: {url}")
    try:
        with _page_lock:
            html = http_fetch.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        code = extract_product_code(url)
        image_urls = extract_image_urls(soup)

        for idx, img_url in enumerate(image_urls):
            img_path = IMAGE_DIR / f"{code}_{idx + 1}.jpg"
            download_image(img_url, img_path)
    except Exception as e:
        print(f"❌ 图片处理失败: {url} → {e}")


def fetch_urls_from_db_by_codes(code_file_path, pgsql_config, table_name):
    code_list = [line.strip() for line in Path(code_file_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"🔍 共读取到 {len(code_list)} 个商品编码")

    urls = set()
    try:
        conn = psycopg2.connect(**pgsql_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        placeholders = ",".join(["%s"] * len(code_list))
        query = f"""
            SELECT DISTINCT product_code, product_url
            FROM {table_name}
            WHERE product_code IN ({placeholders})
        """
        cursor.execute(query, code_list)
        rows = cursor.fetchall()

        code_to_url = {row["product_code"]: row["product_url"] for row in rows}
        for code in code_list:
            url = code_to_url.get(code)
            if url:
                urls.add(url)
            else:
                print(f"⚠️ 编码未找到: {code}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")

    return list(urls)


def download_images_by_code_file(code_txt_path):
    pgsql_config = CLARKS["PGSQL_CONFIG"]
    table_name = CLARKS["TABLE_NAME"]

    urls = fetch_urls_from_db_by_codes(code_txt_path, pgsql_config, table_name)
    print(f"📦 共需下载 {len(urls)} 个商品的图片\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_only, url) for url in urls]
        for future in as_completed(futures):
            future.result()

    print("\n✅ 所有指定商品图片下载完成")


def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 链接文件不存在: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"📦 共 {len(urls)} 个商品图片待处理")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_only, url) for url in urls]
        for future in as_completed(futures):
            future.result()

    print("\n✅ 所有图片下载完成")

def download_all_images_from_product_links():
    main()


if __name__ == "__main__":
    main()  # 处理 product_links.txt 中所有链接
