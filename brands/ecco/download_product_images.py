# -*- coding: utf-8 -*-
"""
ECCO 商品图片下载（兼容新版站点）
- 解析 <img>/<source> 的 srcset，挑最大尺寸
- 从文件名解析 6位款号+5位色号+视角，规范命名保存
- 兼容 .png/.webp/.jpg，去重避免重复下载
- 兼容从 URL 或图片名回退提取编码
- 保留原有 pipeline 入口函数与参数
"""

import time
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

# === 你的项目内配置 ===
from config import ECCO, ensure_all_dirs, GLOBAL_CHROMEDRIVER_PATH
from selenium.webdriver.chrome.service import Service

# ---------------- 基本配置 ----------------
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = ECCO["IMAGE_DOWNLOAD"]
WAIT = 0                # 打开页面后的静态等待（若需可调大）
DELAY = 0               # 每张图下载的节流间隔（秒）
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5         # 并发线程数（对 URL 任务的并发，不是图片）

# 确保目录存在
ensure_all_dirs(IMAGE_DIR)

# ============== WebDriver ==============
def create_driver():
    opts = Options()
    for a in ["--headless=new", "--disable-gpu", "--no-sandbox",
              "--disable-dev-shm-usage", "--window-size=1920x1080"]:
        opts.add_argument(a)
    return webdriver.Chrome(service=Service(GLOBAL_CHROMEDRIVER_PATH), options=opts)

# ============== 工具函数：srcset 解析/命名规范 ==============
_VIEW_TOKEN = r"(?:o|m|b|s|top_left_pair|front_pair)"
_EXT_TOKEN  = r"(?:png|webp|jpg|jpeg)"

def _strip_query(url: str) -> str:
    """去掉 URL 查询参数（命名时用），下载可保留原始 URL。"""
    u = urlparse(url)
    return urlunparse(u._replace(query=""))

def _pick_largest_from_srcset(srcset: str) -> str | None:
    """从 srcset 字符串中选 width 最大的 URL。"""
    best_url, best_w = None, -1
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split()
        url = pieces[0]
        w = 0
        if len(pieces) > 1 and pieces[1].endswith("w"):
            try:
                w = int(pieces[1][:-1])
            except:
                w = 0
        if w > best_w:
            best_url, best_w = url, w
    return best_url

def _iter_image_candidate_urls(soup: BeautifulSoup):
    """遍历页面中可能的商品图 URL，优先取 srcset 的最大尺寸。"""
    # <img>
    for img in soup.find_all("img"):
        srcset = img.get("srcset")
        if srcset:
            best = _pick_largest_from_srcset(srcset)
            if best:
                yield best
                continue
        for key in ("src", "data-src", "data-original"):
            if img.get(key):
                yield img.get(key)

    # <source>
    for tag in soup.find_all("source"):
        srcset = tag.get("srcset")
        if srcset:
            best = _pick_largest_from_srcset(srcset)
            if best:
                yield best

def _parse_code_view_from_filename(url: str) -> tuple[str | None, str | None, str | None, str]:
    """
    从 URL 文件名解析 (style6, color5, view, ext)
    兼容：470824-51866-m_eCom.png / 470824-51866-top_left_pair.webp / 470824-51866-o.png 等
    """
    no_q = _strip_query(url).lower()
    path = urlparse(no_q).path
    fname = Path(path).name  # e.g. 470824-51866-o_ecom.png

    # 1) -<view>_eCom.<ext>
    m = re.search(fr"(\d{{6}})-(\d{{5}})-({_VIEW_TOKEN})_ecom\.{_EXT_TOKEN}$", fname, flags=re.I)
    if not m:
        # 2) -<view>.<ext>
        m = re.search(fr"(\d{{6}})-(\d{{5}})-({_VIEW_TOKEN})\.{_EXT_TOKEN}$", fname, flags=re.I)

    if m:
        style6, color5, view = m.group(1), m.group(2), m.group(3).lower()
        ext = Path(path).suffix.lower()
        return style6, color5, view, ext

    # 3) 只解析 6+5
    m2 = re.search(r"(\d{6})-(\d{5})", fname)
    ext = Path(path).suffix.lower()
    if m2:
        return m2.group(1), m2.group(2), None, ext

    return None, None, None, ext

def _normalize_save_name(url: str, fallback_code: str | None) -> tuple[str, str]:
    """
    生成保存名 (basename, ext)。优先用 6+5+view；否则用 6+5；否则 fallback；仍无则用文件名兜底。
    basename 不含扩展名；ext 以 URL 实际扩展名为准（.png/.webp/.jpg）
    """
    style6, color5, view, ext = _parse_code_view_from_filename(url)
    if style6 and color5 and view:
        return f"{style6}{color5}_{view}", ext
    if style6 and color5:
        return f"{style6}{color5}", ext
    if fallback_code:
        return fallback_code, ext

    stem = Path(urlparse(_strip_query(url)).path).stem
    return stem.replace("-", "_"), ext

def _extract_code_from_url(u: str) -> str | None:
    """从新版 URL /product/.../<6位>/<5位> 提取编码"""
    m = re.search(r'/(\d{6})/(\d{5})(?:[/?#]|$)', u)
    if m:
        return m.group(1) + m.group(2)
    return None

def _extract_code_from_images_html(html: str) -> str | None:
    """从整页 HTML 中的图片文件名提取 6+5 编码（回退用）"""
    m = re.search(r'/(\d{6})-(\d{5})-(?:' + _VIEW_TOKEN + r')\.(?:' + _EXT_TOKEN + r')', html, flags=re.I)
    if m:
        return m.group(1) + m.group(2)
    m2 = re.search(r'/(\d{6})-(\d{5})\.', html)
    if m2:
        return m2.group(1) + m2.group(2)
    return None

# ============== 下载主逻辑（新版解析） ==============
def download_images_from_soup(soup: BeautifulSoup, formatted_code: str | None):
    """
    扫描页面的商品图片并下载：
    - 优先取 srcset 最大尺寸
    - 规范命名（6位款号+5位色号+视角）
    - 去重（同图不同尺寸只取一次）
    """
    seen_basenames = set()

    for raw_url in _iter_image_candidate_urls(soup):
        if not raw_url:
            continue

        # 仅接受图片资源
        lower_url = raw_url.lower()
        if not any(ext in lower_url for ext in (".png", ".webp", ".jpg", ".jpeg")):
            continue

        # 生成保存名
        basename, ext = _normalize_save_name(raw_url, formatted_code)
        if basename in seen_basenames:
            continue
        seen_basenames.add(basename)

        save_path = IMAGE_DIR / f"{basename}{ext}"
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 跳过: {save_path.name}")
            continue

        try:
            resp = requests.get(raw_url, timeout=20)
            resp.raise_for_status()
            save_path.write_bytes(resp.content)
            print(f"🖼️ 下载: {save_path.name}")
            time.sleep(DELAY)
        except Exception as e:
            print(f"❌ 下载失败: {raw_url} - {e}")

# ============== 单页处理：保持原函数名与参数 ==============
def process_image_url(url):
    """
    打开商品页 → 提取编码（URL / 图片名回退）→ 扫描并下载所有商品图
    """
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)

        real_url = driver.current_url or url
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # 老站点的 DOM（兼容旧数据源），若存在就优先
        formatted_code = None
        code_info = soup.find('div', class_='product_info__product-number')
        if code_info:
            try:
                text = code_info.text.strip()
                # 旧逻辑：形如 "... Product no. 47082451866 ..."
                digits = re.search(r'(\d{11})', text)
                if digits:
                    formatted_code = digits.group(1)
            except Exception:
                formatted_code = None

        # 新站点：从 URL 提取 6+5
        if not formatted_code:
            formatted_code = _extract_code_from_url(real_url)

        # 回退：从页面图片文件名中提取 6+5
        if not formatted_code:
            formatted_code = _extract_code_from_images_html(html)

        download_images_from_soup(soup, formatted_code)

    except Exception as e:
        print(f"❌ 商品处理失败: {url} - {e}")
    finally:
        if driver:
            driver.quit()

# ============== 批量入口：与原来保持一致 ==============
from concurrent.futures import ThreadPoolExecutor, as_completed

def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 未找到链接文件: {PRODUCT_LINKS_FILE}")
        return
    url_list = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"\n📸 开始下载 {len(url_list)} 个商品的图片...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_url, url) for url in url_list]
        for _ in as_completed(futures):
            pass

    print("\n✅ 所有图片下载完成。")

# ============== 根据编码补图：与原来保持一致 ==============
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
    pgsql_config = ECCO["PGSQL_CONFIG"]
    table_name = ECCO["TABLE_NAME"]

    urls = fetch_urls_from_db_by_codes(code_txt_path, pgsql_config, table_name)
    print(f"📦 共需处理 {len(urls)} 个商品图片")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_url, url) for url in urls]
        for _ in as_completed(futures):
            pass

    print("\n✅ 所有补图完成")

# ------------- 脚本直接运行时的默认入口 -------------
if __name__ == "__main__":
    # main()  # 正常：按 product_links.txt 批量下载

    # 补图模式：按编码文件
    code_txt_path = ECCO["BASE"] / "publication" / "补图编码.txt"
    download_images_by_code_file(code_txt_path)
