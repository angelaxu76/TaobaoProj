import time
import re
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config import ECCO, ensure_all_dirs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 配置 ===
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = ECCO["IMAGE_DIR"]
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
WAIT = 0
DELAY = 0
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5  # 并发线程数

# 确保目录存在
ensure_all_dirs(IMAGE_DIR)

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)

def download_images_from_soup(soup, formatted_code):
    for img in soup.select("div.product_details__media-item-img img"):
        if "src" not in img.attrs:
            continue
        img_url = img["src"].replace("DetailsMedium", "ProductDetailslarge3x")
        match = re.search(r'/([0-9A-Za-z-]+-(?:o|m|b|s|top_left_pair|front_pair))\.webp', img_url)
        img_code = match.group(1) if match else formatted_code
        img_path = IMAGE_DIR / f"{img_code}.webp"

        if SKIP_EXISTING_IMAGE and img_path.exists():
            print(f"✅ 跳过: {img_path.name}")
            continue

        try:
            with open(img_path, "wb") as f:
                f.write(requests.get(img_url, timeout=10).content)
            print(f"🖼️ 下载: {img_path.name}")
            time.sleep(DELAY)
        except Exception as e:
            print(f"❌ 下载失败: {img_url} - {e}")

def process_image_url(url):
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        code_info = soup.find('div', class_='product_info__product-number')
        if not code_info:
            print(f"⚠️ 未找到编码，跳过: {url}")
            return

        product_code = code_info.text.strip().split()[2]
        code, color = product_code[:6], product_code[6:]
        formatted_code = f"{code}-{color}"

        download_images_from_soup(soup, formatted_code)

    except Exception as e:
        print(f"❌ 商品处理失败: {url} - {e}")
    finally:
        if driver:
            driver.quit()

def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 未找到链接文件: {PRODUCT_LINKS_FILE}")
        return
    url_list = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"\n📸 开始下载 {len(url_list)} 个商品的图片...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_url, url) for url in url_list]
        for future in as_completed(futures):
            pass

    print("\n✅ 所有图片下载完成。")

# === 新增功能：根据商品编码下载图片 ===
import psycopg2
from psycopg2.extras import RealDictCursor

def fetch_urls_from_db_by_codes(code_file_path, pgsql_config, table_name):
    code_list = [line.strip() for line in Path(code_file_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"🔍 读取到 {len(code_list)} 个编码")

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
                print(f"⚠️ 未找到商品编码: {code}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")

    return list(urls)

def download_images_by_code_file(code_txt_path):
    from config import ECCO
    pgsql_config = ECCO["PGSQL_CONFIG"]
    table_name = ECCO["TABLE_NAME"]

    urls = fetch_urls_from_db_by_codes(code_txt_path, pgsql_config, table_name)
    print(f"📦 共需处理 {len(urls)} 个商品图片")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_url, url) for url in urls]
        for future in as_completed(futures):
            pass

    print("\n✅ 所有补图完成")

if __name__ == "__main__":
    # main()  # 正常处理 product_links.txt 中全部链接

    # 👇 补图模式
    code_txt_path = ECCO["BASE"] / "publication" / "补图编码.txt"
    download_images_by_code_file(code_txt_path)