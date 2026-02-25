# fetch_product_info.py
import os
import re
import time
import json
import threading

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CAMPER, SIZE_RANGE_CONFIG  # ✅ 引入标准尺码配置
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category
from selenium import webdriver
driver = webdriver.Chrome()
from common.browser.selenium_utils import get_driver

PRODUCT_URLS_FILE = CAMPER["LINKS_FILE"]
SAVE_PATH = CAMPER["TXT_DIR"]
MAX_WORKERS = 6

os.makedirs(SAVE_PATH, exist_ok=True)

def infer_gender_from_url(url: str) -> str:
    url = url.lower()
    if "/women/" in url:
        return "女款"
    elif "/men/" in url:
        return "男款"
    elif "/kids/" in url or "/children/" in url:
        return "童款"
    return "未知"

def create_driver():
    from selenium import webdriver
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

    # ✅ 不再手动指定路径，也不使用 chromedriver_autoinstaller
    driver = webdriver.Chrome(options=chrome_options)

    # 打印版本确认匹配
    try:
        caps = driver.capabilities
        print("Chrome:", caps.get("browserVersion"))
        print("ChromeDriver:", (caps.get("chrome") or {}).get("chromedriverVersion", ""))
    except Exception:
        pass

    return driver



# === 新增：全局记录 driver 并统一回收，避免多轮运行残留进程 ===
drivers_lock = threading.Lock()
_all_drivers = set()

thread_local = threading.local()
# common/selenium_utils.py

def get_driver():
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    import undetected_chromedriver as uc

    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(options=options)
    return driver


def shutdown_all_drivers():
    # 任务结束统一关闭所有无头浏览器，防泄漏
    with drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except Exception:
                pass
        _all_drivers.clear()

def process_product_url(PRODUCT_URL):
    try:
        driver = get_driver()
        print(f"\n🔍 正在访问: {PRODUCT_URL}")
        driver.get(PRODUCT_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        title_tag = soup.find("title")
        product_title = re.sub(r"\s*[-–—].*", "", title_tag.text.strip()) if title_tag else "Unknown Title"

        script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
        if not script_tag:
            print("⚠️ 未找到 JSON 数据")
            return

        json_data = json.loads(script_tag.string)
        product_sheet = json_data.get("props", {}).get("pageProps", {}).get("productSheet")
        if not product_sheet:
            print(f"⚠️ 未找到 productSheet，跳过: {PRODUCT_URL}")
            return
        data = product_sheet

        product_code = data.get("code", "Unknown_Code")
        product_url = PRODUCT_URL
        description = data.get("description", "")

        price_info = data.get("prices", {})
        original_price = price_info.get("previous", 0)
        discount_price = price_info.get("current", 0)

        color_data = data.get("color", "")
        color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

        # === 提取 features ===
        features_raw = data.get("features") or []  # ✅ 保证是列表
        feature_texts = []
        for f in features_raw:
            try:
                value_html = f.get("value", "")
                clean_text = BeautifulSoup(value_html, "html.parser").get_text(strip=True)
                if clean_text:
                    feature_texts.append(clean_text)
            except Exception as e:
                print(f"⚠️ Feature 解析失败: {e}")
        feature_str = " | ".join(feature_texts) if feature_texts else "No Data"

        # === 提取 Upper 材质（优先 features） ===
        upper_material = "No Data"
        for feature in features_raw:
            name = (feature.get("name") or "").lower()
            if "upper" in name:
                raw_html = feature.get("value") or ""
                upper_material = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
                break

        # === 提取尺码、库存、EAN ===
        size_map = {}
        size_detail = {}
        for size in data.get("sizes", []):
            value = size.get("value", "").strip()
            available = size.get("available", False)
            quantity = size.get("quantity", 0)
            ean = size.get("ean", "")
            size_map[value] = "有货" if available else "无货"
            size_detail[value] = {
                "stock_count": quantity,
                "ean": ean
            }

        gender = infer_gender_from_url(PRODUCT_URL)

        # ✅ 尺码补全逻辑
        standard_sizes = SIZE_RANGE_CONFIG.get("camper", {}).get(gender, [])
        if standard_sizes:
            missing_sizes = [s for s in standard_sizes if s not in size_detail]
            for s in missing_sizes:
                size_map[s] = "无货"
                size_detail[s] = {"stock_count": 0, "ean": ""}
            if missing_sizes:
                print(f"⚠️ {product_code} 补全尺码: {', '.join(missing_sizes)}")

        style_category = infer_style_category(description)
        # === 整理 info 字典 ===
        info = {
            "Product Code": product_code,
            "Product Name": product_title,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": str(original_price),
            "Adjusted Price": str(discount_price),
            "Product Material": upper_material,
            "Style Category": style_category,  # ✅ 新增字段
            "Feature": feature_str,
            "SizeMap": size_map,
            "SizeDetail": size_detail,
            "Source URL": product_url
        }

        # === 写入 TXT 文件 ===
        filepath = SAVE_PATH / f"{product_code}.txt"
        format_txt(info, filepath, brand="camper")
        print(f"✅ 完成 TXT: {filepath.name}")

    except Exception as e:
        print(f"❌ 错误: {PRODUCT_URL} - {e}")

def camper_fetch_product_info(product_urls_file=None, max_workers=MAX_WORKERS):
    """
    Camper 商品抓取主入口。
    :param product_urls_file: 可选，自定义的 product_links.txt 路径。如果为 None，则使用 config 中的 CAMPER["LINKS_FILE"]。
    :param max_workers: 线程数。
    """
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    print(f"📄 使用链接文件: {product_urls_file}")

    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_product_url, url) for url in urls]
            for future in as_completed(futures):
                future.result()
    finally:
        # ✅ 关键：每轮任务结束都关闭全部 driver，避免残留进程堆积
        shutdown_all_drivers()


# === New: URL->code 解析与缺失补抓工具 ===
import re
from pathlib import Path
from urllib.parse import urlparse

CODE_PATTERNS = [
    r"[AK]\d{6}-\d{3}",     # K100743-003 / A700019-001
    r"\d{5,6}-\d{3}",       # 90203-051 / 16002-323 等
]
CODE_REGEX = re.compile(r"(" + "|".join(CODE_PATTERNS) + r")")

def normalize_url(u: str) -> str:
    u = u.strip()
    if not u:
        return u
    if not u.startswith("http"):
        u = "https://" + u.lstrip("/")
    return u

def code_from_url(u: str) -> str | None:
    u = normalize_url(u)
    m = list(CODE_REGEX.finditer(u))
    return m[-1].group(0) if m else None  # 取最后一个匹配，最稳妥

def load_all_urls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [normalize_url(x) for x in (line.strip() for line in f) if x.strip()]

def existing_codes_from_txt_dir(txt_dir: str) -> set[str]:
    p = Path(txt_dir)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    return {fn.stem.upper() for fn in p.glob("*.txt")}

def expected_maps(urls: list[str]) -> dict[str, str]:
    # 返回 {code: url}
    mapping = {}
    for u in urls:
        c = code_from_url(u)
        if c:
            mapping[c.upper()] = u
    return mapping

def run_batch_fetch(urls: list[str], max_workers: int = MAX_WORKERS):
    # 复用你已有的并发抓取逻辑，但只投递给定 urls
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_product_url, u) for u in urls]
            for fut in as_completed(futures):
                fut.result()
    finally:
        shutdown_all_drivers()  # 你已有的统一回收，防泄漏

def camper_fetch_all_with_retry(
    product_urls_file=None,
    txt_dir: str = str(SAVE_PATH),
    max_passes: int = 3,
    first_pass_workers: int = MAX_WORKERS,
    retry_workers: int = 6
):
    
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    all_urls = load_all_urls(product_urls_file)
    code2url = expected_maps(all_urls)

    print(f"📦 总链接数：{len(all_urls)}")
    print(f"📁 TXT 目录：{txt_dir}")

    # 第1轮：全量
    print(f"\n==> Pass 1 / {max_passes}: 全量抓取 {len(all_urls)} 条")
    run_batch_fetch(all_urls, max_workers=first_pass_workers)

    for i in range(2, max_passes + 1):
        have = existing_codes_from_txt_dir(txt_dir)
        need = set(code2url.keys())
        missing_codes = sorted((need - have))

        print(f"\n🔍 Pass {i} 检查缺失:")
        print(f"    已有TXT数量：{len(have)}")
        print(f"    应有总数：{len(need)}")
        print(f"    缺失数量：{len(missing_codes)}")

        if not missing_codes:
            print("🎉 没有缺失，任务完成。")
            break

        # 打印部分缺失编码预览
        print("    缺失编码示例：", ", ".join(missing_codes[:10]), "..." if len(missing_codes) > 10 else "")

        # 生成缺失名单与对应 URL 列表
        missing_urls = [code2url[c] for c in missing_codes if c in code2url]
        miss_list_path = Path(txt_dir) / f"missing_camper_pass{i}.txt"
        with open(miss_list_path, "w", encoding="utf-8") as f:
            for c in missing_codes:
                f.write(f"{c}\t{code2url.get(c,'')}\n")

        print(f"🧾 已写入缺失清单：{miss_list_path}")
        print(f"🚀 开始补抓 {len(missing_urls)} 条链接...")

        # 执行补抓
        run_batch_fetch(missing_urls, max_workers=retry_workers)

        # 抓取后再检查数量变化
        after_have = existing_codes_from_txt_dir(txt_dir)
        new_files = sorted(after_have - have)
        print(f"✅ Pass {i} 结束后新增 {len(new_files)} 个TXT。")
        if new_files:
            print("    新增文件示例：", ", ".join(new_files[:10]), "..." if len(new_files) > 10 else "")

    # 收尾汇总
    have_final = existing_codes_from_txt_dir(txt_dir)
    need_final = set(code2url.keys())
    still_missing = sorted(need_final - have_final)
    summary_path = Path(txt_dir) / "missing_camper_final.txt"
    if still_missing:
        with open(summary_path, "w", encoding="utf-8") as f:
            for c in still_missing:
                f.write(f"{c}\t{code2url.get(c,'')}\n")
        print(f"\n⚠️ 仍有 {len(still_missing)} 条未抓到，清单见: {summary_path}")
    else:
        if summary_path.exists():
            summary_path.unlink(missing_ok=True)
        print("\n✅ 最终没有缺失。")

def camper_retry_missing_once(product_urls_file=None):
    """
    仅补抓缺失的 TXT，不跑全量。
    可反复调用多次以进一步补齐。

    :param product_urls_file: 可选，自定义 links 文件。不传则使用 config 默认。
    """
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    txt_dir = str(SAVE_PATH)
    max_workers = 6
    preview = 30

    all_urls = load_all_urls(product_urls_file)
    code2url = expected_maps(all_urls)

    have = existing_codes_from_txt_dir(txt_dir)
    need = set(code2url.keys())
    missing_codes = sorted(need - have)

    print("\n🔁 Camper Retry Missing Once")
    print("📦 总链接数：", len(all_urls))
    print("📁 TXT 目录：", txt_dir)
    print("🧮 已有TXT：", len(have))
    print("❌ 缺失数量：", len(missing_codes))

    if not missing_codes:
        print("🎉 没有缺失可补抓。")
        return

    print("📝 缺失编码示例：", ", ".join(missing_codes[:preview]), "..." if len(missing_codes) > preview else "")

    missing_urls = [code2url[c] for c in missing_codes if c in code2url]
    miss_list_path = Path(txt_dir) / "missing_camper_once.txt"
    with open(miss_list_path, "w", encoding="utf-8") as f:
        for c in missing_codes:
            f.write(f"{c}\t{code2url.get(c,'')}\n")

    print(f"🧾 已写入缺失清单：{miss_list_path}")
    print(f"🚀 开始补抓缺失 {len(missing_urls)} 条……")

    run_batch_fetch(missing_urls, max_workers=max_workers)

    after = existing_codes_from_txt_dir(txt_dir)
    new_files = sorted(after - have)
    print(f"✅ 本次补抓新增 TXT：{len(new_files)}")
    if new_files:
        print("📂 新增文件预览：", ", ".join(new_files[:preview]), "..." if len(new_files) > preview else "")



if __name__ == "__main__":
    camper_fetch_product_info()
