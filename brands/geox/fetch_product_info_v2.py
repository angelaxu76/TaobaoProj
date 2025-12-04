import os
import re
import time
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import SessionNotCreatedException

from config import SIZE_RANGE_CONFIG, GEOX
from common_taobao.ingest.txt_writer import format_txt
from common_taobao.core.category_utils import infer_style_category

# ===================== 基本配置 =====================
PRODUCT_LINK_FILE = GEOX["BASE"] / "publication" / "product_links.txt"
TXT_OUTPUT_DIR = GEOX["TXT_DIR"]
BRAND = "geox"

# 建议：4~8 之间按电脑性能调
MAX_THREADS = 6

# 手动登录等待时间（登录窗口只出现一次）
LOGIN_WAIT_SECONDS = 20

TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===================== Chrome Profile（登录用） =====================
# ⚠ 登录用 driver：使用你原来配置的 Profile（有折扣/登录态）
PROFILE_ROOT = r"D:\ChromeProfiles\AutoProfile_GEOX"   # 非默认目录根
PROFILE_NAME = "Profile 2"                             # 子目录名：Profile 1/2/3/4/Default 等
FIXED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ===================== 登录 driver（可见窗口） =====================
def _build_options(headless: bool = False,
                   user_data_dir: str = PROFILE_ROOT,
                   profile_name: str = PROFILE_NAME) -> Options:
    chrome_options = Options()

    if headless:
        chrome_options.add_argument("--headless=new")

    # 如有需要，改成你真实 Chrome 路径
    chrome_options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    # ✅ 复用已存在的 Profile（关键）
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument(f"--profile-directory={profile_name}")

    # 稳定参数
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(f"user-agent={FIXED_UA}")

    return chrome_options


def _kill_chrome():
    os.system('taskkill /F /IM chrome.exe /T')
    os.system('taskkill /F /IM chromedriver.exe /T')


def create_login_driver() -> webdriver.Chrome:
    """用于手动/自动登录的一次性可见窗口 driver。"""
    print("Using user-data-dir =", PROFILE_ROOT)
    print("Using profile-directory =", PROFILE_NAME)
    try:
        opts = _build_options(headless=False)
        driver = webdriver.Chrome(options=opts)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        print(
            "Chrome =", driver.capabilities.get("browserVersion"),
            "| Chromedriver =",
            driver.capabilities.get("chrome", {}).get("chromedriverVersion")
        )
        return driver
    except SessionNotCreatedException:
        _kill_chrome()
        time.sleep(0.5)
        opts = _build_options(headless=False)
        driver = webdriver.Chrome(options=opts)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        print(
            "Chrome =", driver.capabilities.get("browserVersion"),
            "| Chromedriver =",
            driver.capabilities.get("chrome", {}).get("chromedriverVersion")
        )
        return driver


# ===================== Worker driver（多线程 headless） =====================
def create_worker_driver() -> webdriver.Chrome:
    """
    多线程 worker 使用的轻量 driver：
    - headless
    - 禁图
    - pageLoadStrategy=eager
    """
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--disable-gpu")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--window-size=1920,1080")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # 禁图，进一步提速
    o.add_argument("--blink-settings=imagesEnabled=false")
    # DOMContentLoaded 即返回
    o.set_capability("pageLoadStrategy", "eager")

    d = webdriver.Chrome(options=o)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    return d


# ===================== 会话导出 / 导入 =====================
def export_session(driver: webdriver.Chrome) -> Dict:
    """导出 cookies + localStorage，供并发线程复用登录态。"""
    cookies = driver.get_cookies()
    ls_items = driver.execute_script(
        """
        const out = {};
        for (let i=0; i<localStorage.length; i++){
            const k = localStorage.key(i);
            out[k] = localStorage.getItem(k);
        }
        return out;
        """
    )
    return {"cookies": cookies, "localStorage": ls_items}


def import_session(driver: webdriver.Chrome,
                   session: Dict,
                   base_url: str = "https://www.geox.com/") -> None:
    """将 cookies + localStorage 注入到新 driver。必须先打开同域页面。"""
    driver.get(base_url)

    # 写入 cookies
    for c in session.get("cookies", []):
        to_add = {
            "name": c.get("name"),
            "value": c.get("value"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        }
        if c.get("domain"):
            to_add["domain"] = c["domain"]
        if c.get("expiry"):
            to_add["expiry"] = c["expiry"]
        try:
            driver.add_cookie(to_add)
        except Exception as e:
            print(f"cookie 注入失败 {to_add.get('name')}: {e}")

    # 写入 localStorage
    driver.execute_script("localStorage.clear();")
    for k, v in session.get("localStorage", {}).items():
        driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k, v)


# ===================== 页面抓取 =====================
def get_html(driver: webdriver.Chrome, url: str) -> Optional[str]:
    def _accept_cookies():
        for sel in [
            "button#onetrust-accept-btn-handler",
            "button.cookie-accept",
            "button.js-accept-all",
        ]:
            try:
                btn = WebDriverWait(driver, 0.1).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                time.sleep(0)
                return
            except Exception:
                continue

    def _scroll_warmup():
        driver.execute_script("window.scrollTo(0, 400);"); time.sleep(0)
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight - 400);"
        ); time.sleep(0)
        driver.execute_script("window.scrollTo(0, 0);"); time.sleep(0)

    driver.get(url)
    _accept_cookies()

    try:
        WebDriverWait(driver, 0.1).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.product-info div.price, "
                    "div.right-side div.price, "
                    "div.price-mobile div.price, "
                    "div.price",
                )
            )
        )
        WebDriverWait(driver, 0.1).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.add-to-cart"))
        )
    except Exception:
        pass

    _scroll_warmup()

    try:
        WebDriverWait(driver, 0.1).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "span.product-price span.sales span.value[content]",
                )
            )
        )
        try:
            WebDriverWait(driver, 1).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "span.product-price span.sales.discount span.value[content]",
                    )
                )
            )
        except Exception:
            pass
    except Exception:
        pass

    try:
        WebDriverWait(driver, 0.1).until(
            lambda d: (
                d.execute_script(
                    """
                    const btn = document.querySelector('button.add-to-cart');
                    if(!btn) return false;
                    try {
                        return typeof JSON.parse(
                            btn.getAttribute('data-gtmdata') || '{}'
                        ).item_promo === 'string';
                    } catch(e){ return false; }
                    """
                )
                is True
            )
        )
    except Exception:
        pass

    time.sleep(0)
    return driver.page_source


# ===================== 业务解析逻辑（基本保持你原来的） =====================
def supplement_geox_sizes(size_stock: Dict[str, str], gender: str) -> Dict[str, str]:
    standard_sizes = SIZE_RANGE_CONFIG.get("geox", {}).get(gender, [])
    for size in standard_sizes:
        if size not in size_stock:
            size_stock[size] = "0"  # 无货
    return size_stock


def detect_gender_by_code(code: str) -> str:
    if not code:
        return "未知"
    code = code.strip().upper()
    if code.startswith("D"):
        return "女款"
    if code.startswith("U"):
        return "男款"
    if code.startswith("J"):
        return "童款"
    return "未知"


def parse_product(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    # 基本信息
    code_tag = soup.select_one("span.product-id")
    code = code_tag.text.strip() if code_tag else "No Data"

    name_tag = soup.select_one("div.sticky-image img")
    name = (
        name_tag["alt"].strip()
        if name_tag is not None and name_tag.has_attr("alt")
        else "No Data"
    )

    # 价格（仅限 PDP 主区域；排除推荐/轮播；区间价取最大）
    def _safe_select_value(_soup, selector: str):
        for node in _soup.select(selector):
            if node.find_parent(class_="product-tile") or node.find_parent(
                class_="product-carousel-tile"
            ):
                continue
            return node
        return None

    def extract_max_price(val):
        if not val:
            return "No Data"
        s = str(val).strip()
        if "-" in s:
            try:
                parts = [float(p.strip()) for p in s.split("-") if p.strip()]
                return f"{max(parts):.2f}"
            except Exception:
                return s
        return s

    price_tag = _safe_select_value(soup, "span.product-price span.value")
    discount_tag = _safe_select_value(
        soup, "span.sales.discount span.value"
    )

    full_price_raw = (
        (price_tag.get("content") or price_tag.get_text(strip=True).replace("£", ""))
        .strip()
        if price_tag
        else ""
    )
    discount_price_raw = (
        (
            discount_tag.get("content")
            or discount_tag.get_text(strip=True).replace("£", "")
        ).strip()
        if discount_tag
        else ""
    )

    original_price = extract_max_price(full_price_raw) or "No Data"

    # 折扣价校验：无折扣/异常值，回退原价
    discount_price = extract_max_price(discount_price_raw) if discount_price_raw else ""
    try:
        op = float(original_price) if original_price not in ("", "No Data") else None
        dp = float(discount_price) if discount_price not in ("", "No Data") else None
        if dp is None or op is None or dp >= op or dp < op * 0.3:
            discount_price = original_price
    except Exception:
        discount_price = original_price

    # 颜色 / 材质 / 描述
    color_block = soup.select_one("div.sticky-color")
    color = (
        color_block.get_text(strip=True).replace("Color:", "").strip()
        if color_block
        else "No Data"
    )

    materials_block = soup.select_one("div.materials-container")
    material_text = (
        materials_block.get_text(" ", strip=True) if materials_block else "No Data"
    )

    desc_block = soup.select_one("div.product-description div.value")
    description = desc_block.get_text(strip=True) if desc_block else "No Data"

    # 性别
    gender = detect_gender_by_code(code)

    # 尺码库存
    size_blocks = soup.select("div.size-value")
    size_stock: Dict[str, str] = {}
    for sb in size_blocks:
        size = (
            sb.get("data-attr-value")
            or sb.get("prodsize")
            or sb.get("aria-label")
        )
        size = size.strip().replace(",", ".") if size else "Unknown"
        available = "1" if "disabled" not in sb.get("class", []) else "0"
        size_stock[size] = available

    size_stock = supplement_geox_sizes(size_stock, gender)

    # Jingya 模式：输出 SizeMap / SizeDetail
    size_map: Dict[str, str] = {}
    size_detail: Dict[str, Dict] = {}
    for eu, flag in size_stock.items():
        has = str(flag) == "1"
        size_map[eu] = "有货" if has else "无货"
        size_detail[eu] = {"stock_count": 3 if has else 0, "ean": "0000000000000"}

    # 风格分类
    style_category = infer_style_category(f"{name} {description}")

    info = {
        "Product Code": code,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": original_price,
        "Adjusted Price": discount_price,
        "Product Material": material_text,
        "Style Category": style_category,
        "Feature": "No Data",
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Source URL": url,
    }
    return info


def derive_code_from_url(url: str) -> str:
    """从 URL 末尾提取商品编码（“-<code>.html”）。"""
    try:
        path = urlparse(url).path
        name = Path(path).name
        base = name.split("?", 1)[0]
        token = base.rsplit("-", 1)[-1]
        code = token.split(".", 1)[0].upper()
        if len(code) < 6 or not any(ch.isdigit() for ch in code):
            m = re.search(r"([A-Za-z0-9]{6,})\.html$", base)
            if m:
                code = m.group(1).upper()
        return code
    except Exception:
        return Path(urlparse(url).path).stem.upper()


# ===================== 多线程抓取核心 =====================
_thread_local = threading.local()
_DRIVER_LIST_LOCK = threading.Lock()
_THREAD_DRIVERS: List[webdriver.Chrome] = []


def _get_thread_driver(session: Dict) -> webdriver.Chrome:
    """每个线程懒加载一个 headless driver，并注入 session。"""
    driver = getattr(_thread_local, "driver", None)
    if driver is None:
        driver = create_worker_driver()
        import_session(driver, session, base_url="https://www.geox.com/")
        with _DRIVER_LIST_LOCK:
            _THREAD_DRIVERS.append(driver)
        _thread_local.driver = driver
    return driver


def _process_one_url(
    idx: int, total: int, url: str, session: Dict
) -> Tuple[bool, str]:
    driver = _get_thread_driver(session)
    try:
        print(f"[{idx}/{total}] 抓取: {url}")
        html = get_html(driver, url)
        if not html:
            print(f"[{idx}] ⚠ 空页面: {url}")
            return False, url

        info = parse_product(html, url)
        if not info:
            print(f"[{idx}] ⚠ 解析失败: {url}")
            return False, url

        # 如果页面没给编码，最后兜底用 URL 推导
        if not info.get("Product Code") or info["Product Code"] == "No Data":
            info["Product Code"] = derive_code_from_url(url)

        code = info["Product Code"]
        txt_path = TXT_OUTPUT_DIR / f"{code}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        format_txt(info, txt_path, brand=BRAND)
        print(f"[{idx}] ✅ 写入成功: {txt_path.name}")
        return True, url

    except Exception as e:
        print(f"[{idx}] ❌ 处理失败 {url} → {e}")
        return False, url


def _cleanup_thread_drivers():
    with _DRIVER_LIST_LOCK:
        for d in _THREAD_DRIVERS:
            try:
                d.quit()
            except Exception:
                pass
        _THREAD_DRIVERS.clear()


# ===================== 主入口 =====================
def fetch_all_product_info(links_file=None, max_workers: int = MAX_THREADS):
    """
    GEOX 商品抓取主入口（支持外部传入 product_links.txt 覆盖默认路径）。
    prepare_jingya_listing.py 里两次调用都兼容：
        fetch_all_product_info()
        fetch_all_product_info(missing_product_link)
    """
    # 1) 解析链接文件
    if links_file is None:
        links_path = PRODUCT_LINK_FILE
    else:
        links_path = Path(links_file)

    if not links_path.exists():
        print(f"❌ 缺少链接文件: {links_path}")
        return

    with open(links_path, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip()]

    if not urls:
        print(f"⚠ 链接列表为空: {links_path}")
        return

    total = len(urls)
    print(f"\n📦 本次需要抓取 GEOX 商品数量: {total}")

    # 2) 登录一次，导出 session
    login_driver = create_login_driver()
    try:
        # 打开第一条链接，让你有机会确认登录/折扣
        login_driver.get(urls[0])
        print(
            f"⏳ 如需登录，请在新窗口手动登录 GEOX（等待 {LOGIN_WAIT_SECONDS} 秒）"
        )
        time.sleep(LOGIN_WAIT_SECONDS)
        session = export_session(login_driver)
        print("✅ 登录态已导出，将注入到多线程 worker 中")
    finally:
        login_driver.quit()

    # 3) 多线程抓取
    t0 = time.time()
    success = 0
    fail = 0

    print(f"🚀 启动多线程抓取（线程数: {max_workers}）")
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _process_one_url, idx, total, url, session
                ): url
                for idx, url in enumerate(urls, 1)
            }
            for fut in as_completed(futures):
                ok, _ = fut.result()
                if ok:
                    success += 1
                else:
                    fail += 1
    finally:
        _cleanup_thread_drivers()

    dt = time.time() - t0
    print(
        f"\n✅ GEOX 抓取完成：成功 {success} 条，失败 {fail} 条，"
        f"耗时约 {dt/60:.1f} 分钟"
    )


if __name__ == "__main__":
    fetch_all_product_info()
