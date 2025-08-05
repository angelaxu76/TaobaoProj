import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from pathlib import Path
import time
from config import BARBOUR
from pathlib import Path
import re
import json
from bs4 import BeautifulSoup

# === 配置路径 ===
from config import BARBOUR

# ✅ 页面配置：上衣类（男 + 女）
TARGET_URLS = [
    ("men", "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-menswear/all-barbour-mens-clothing-footwear.sub?s=i&pt=Coats+%26+Jackets%2cGilets+%26+Waistcoats%2cKnitwear"),
    ("women", "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-womenswear/womens-barbour-clothing-footwear-accessories.sub?s=i&pt=Coats+%26+Jackets%2cGilets+%26+Waistcoats%2cKnitwear"),
    ("international", "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour-international/all-barbour-international.sub")
]

BASE_DOMAIN = "https://www.outdoorandcountry.co.uk"
OUTPUT_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
DEBUG_DIR = OUTPUT_FILE.parent / "debug_pages"

SCROLL_STEP = 1200
SCROLL_PAUSE = 1.5
STABLE_THRESHOLD = 10



TXT_DIR = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
LINKS_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]


# === 提取函数 ===
def extract_js_object(js_text: str, var_name: str):
    pattern = re.compile(rf"window\.{re.escape(var_name)}\s*=\s*(\{{.*?\}});", re.DOTALL)
    match = pattern.search(js_text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            print(f"⚠️ 变量 {var_name} 解析失败")
            return {}
    return {}

def parse_outdoor_product_page(html: str, url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")

    # 保存页面调试（可选）
    with open("debug.html", "w", encoding="utf-8") as f:
        f.write(html)

    # 商品名称
    title_tag = soup.find("title")
    if not title_tag:
        return []
    product_name = title_tag.text.strip()

    # URL 中提取颜色
    color = "Unknown"
    if "?c=" in url:
        color = url.split("?c=")[-1].strip().replace("%20", " ").capitalize()

    # 提取 JS 变量
    js_text = soup.text
    colours = extract_js_object(js_text, "Colours")
    sizes = extract_js_object(js_text, "Sizes")
    stock_info = extract_js_object(js_text, "stockInfo")

    if not stock_info:
        print(f"⚠️ 页面无 stockInfo: {url}")
        return []

    results = []
    for k, v in stock_info.items():
        try:
            size_id, color_id = k.split("-")
            size = sizes.get(size_id, size_id)
            color_name = colours.get(color_id, color)
            stock_status = v.get("stockLevelMessage", "").lower()
            price = v.get("priceGbp", 0)

            results.append({
                "Product Name": product_name,
                "Product Color": color_name,
                "Product Size": size,
                "Product URL": url,
                "Stock Status": stock_status,
                "Price": f"{price:.2f}"
            })
        except Exception as e:
            print(f"❌ 解析单项失败: {k} -> {e}")

    return results


# === 写入 TXT ===
def write_txt(filepath: Path, items: list):
    if not items:
        return
    main = items[0]
    lines = [
        f"Product Name: {main['Product Name']}",
        f"Product Color: {main['Product Color']}",
        f"Product URL: {main['Product URL']}",
        f"Product Size: " + "; ".join(f"{i['Product Size']}: {i['Stock Status']}" for i in items),
        f"Product Price: {main['Price']}"
    ]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# === 批量处理逻辑 ===
def outdoorandcountry_fetch_info():
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    urls = set()
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                urls.add(url)

    # ✅ 使用与抓链接完全一样的 uc.Chrome 方式
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options)  # ❌ 不加 headless

    for url in sorted(urls):
        try:
            print(f"\n🌐 打开商品详情页: {url}")
            driver.get(url)
            accept_cookies(driver)
            time.sleep(3)  # ✅ 等待 JS 渲染

            html = driver.page_source

            # ✅ 可选：调试页面截图和 HTML
            with open("debug_product.html", "w", encoding="utf-8") as f:
                f.write(html)
            driver.save_screenshot("debug_product.png")

            items = parse_outdoor_product_page(html, url)
            if items:
                product_name = items[0]['Product Name']
                color = items[0]['Product Color']
                filename = f"{product_name.replace(' ', '_')}_{color}.txt"
                filepath = TXT_DIR / filename
                write_txt(filepath, items)
                print(f"✅ 写入: {filepath.name}")
            else:
                print(f"⚠️ 跳过（无库存信息）: {url}")
        except Exception as e:
            print(f"❌ 错误: {url}\n    {e}")

    driver.quit()


def accept_cookies(driver, timeout=8):
    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        button.click()
        print("🍪 已自动点击 Accept Cookies")
        time.sleep(1)
    except:
        print("⚠️ 未出现 Cookie 接受按钮，可能已接受或被跳过")

def scroll_like_mouse_until_loaded(driver, step=SCROLL_STEP, pause=SCROLL_PAUSE, stable_threshold=STABLE_THRESHOLD):
    print("⚡ 开始加速滚动直到商品全部加载...")
    actions = ActionChains(driver)

    last_count = 0
    stable_count = 0
    total_scrolls = 0

    while True:
        actions.scroll_by_amount(0, step).perform()
        time.sleep(pause)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        current_count = len(soup.select("a.image"))
        print(f"🌀 滚动 {total_scrolls+1} 次后，商品数: {current_count}")

        if current_count == last_count:
            stable_count += 1
        else:
            stable_count = 0
            last_count = current_count

        if stable_count >= stable_threshold:
            print(f"✅ 商品数量稳定（{current_count}），停止滚动")
            break

        total_scrolls += 1

def collect_links_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.select("a.image"):
        href = a.get("href", "").strip()
        if href:
            full_url = href if href.startswith("http") else BASE_DOMAIN + href
            links.add(full_url)
    return links

def outdoorandcountry_fetch_and_save_links():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options, headless=False)

    all_links = set()

    for label, url in TARGET_URLS:
        print(f"\n🚀 打开页面 [{label}]: {url}")
        driver.get(url)
        time.sleep(3)

        accept_cookies(driver)
        scroll_like_mouse_until_loaded(driver)

        print(f"🟡 请检查页面 [{label}] 是否加载完整，可手动再滚动几次")
        input(f"⏸️ 确认 [{label}] 页面加载完成后，按回车继续 >>> ")

        html = driver.page_source
        links = collect_links_from_html(html)
        all_links.update(links)

        debug_file = DEBUG_DIR / f"debug_{label}_auto_scroll.html"
        with debug_file.open("w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ [{label}] 链接提取: {len(links)} 条，页面快照保存: {debug_file}")

    # 保存总链接
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共提取商品链接: {len(all_links)} 条")
    print(f"📄 链接写入: {OUTPUT_FILE}")
    driver.quit()
