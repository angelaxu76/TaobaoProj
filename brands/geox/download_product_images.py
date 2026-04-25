import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import GEOX, ensure_all_dirs, GLOBAL_CHROMEDRIVER_PATH

# === 配置 ===
PRODUCT_LINK_FILE = GEOX["LINKS_FILE"]
IMAGE_OUTPUT_DIR = GEOX["IMAGE_DOWNLOAD"]
CHROMEDRIVER_PATH = GLOBAL_CHROMEDRIVER_PATH
WAIT = 2
DELAY = 0.5
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5  # 建议 3~5 个线程并发

ensure_all_dirs(IMAGE_OUTPUT_DIR)

def create_driver():
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-gcm-driver")
    chrome_options.add_argument("--disable-features=Translate,MediaRouter,AutofillServerCommunication")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def download_image(url, path):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"🖼️ 已保存: {path.name}")
        else:
            print(f"⚠️ 图片获取失败: {url}")
    except Exception as e:
        print(f"❌ 下载失败: {url} → {e}")

def process_image_download(url):
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        code_tag = soup.select_one("span.product-id")
        if not code_tag:
            print(f"⚠️ 未找到编码，跳过: {url}")
            return
        code = code_tag.text.strip()

        image_divs = soup.select("div.product-images div.product-image img")
        for idx, img in enumerate(image_divs):
            src = img.get("data-src")
            if not src or "1024x1024" not in src or code not in src:
                continue
            highres_url = src.replace("1024x1024", "2048x2048")
            suffix_match = re.search(r"_([0-9]{2})\.jpg", src)
            suffix = suffix_match.group(1) if suffix_match else f"{idx}"
            filename = f"{code}_{suffix}.jpg"
            img_path = IMAGE_OUTPUT_DIR / filename

            if SKIP_EXISTING_IMAGE and img_path.exists():
                print(f"✅ 跳过已存在: {img_path.name}")
                continue
            download_image(highres_url, img_path)
    except Exception as e:
        print(f"❌ 下载失败: {url} → {e}")
    finally:
        if driver:
            driver.quit()


import psycopg2
from psycopg2.extras import RealDictCursor

def fetch_geox_urls_by_codes(code_file_path, pgsql_config, table_name):
    code_list = [line.strip() for line in Path(code_file_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"🔍 GEOX编码读取完毕，共 {len(code_list)} 条")

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
                print(f"⚠️ 未找到编码: {code}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库查询出错: {e}")

    return list(urls)

def download_geox_images_by_code_file(code_txt_path):
    print(f"🟢 补图函数开始运行，读取路径: {code_txt_path}")
    pgsql_config = GEOX["PGSQL_CONFIG"]
    table_name = GEOX["TABLE_NAME"]

    urls = fetch_geox_urls_by_codes(code_txt_path, pgsql_config, table_name)
    print(f"📦 GEOX补图任务，共 {len(urls)} 个商品\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_download, url) for url in urls]
        for future in as_completed(futures):
            pass  # 内部已打印日志

    print("\n✅ GEOX 指定商品图片补图完成。")


def main():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return
    urls = [line.strip() for line in PRODUCT_LINK_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"📦 共 {len(urls)} 个商品待下载图片")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_download, url) for url in urls]
        for future in as_completed(futures):
            pass  # 每个线程内已打印日志

    print("\n✅ 所有商品图片下载完成。")

if __name__ == "__main__":
    main()
