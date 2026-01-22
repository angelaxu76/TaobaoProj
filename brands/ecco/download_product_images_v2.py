# -*- coding: utf-8 -*-
"""
ECCO 商品图片下载 V2（兼容新旧站点 + 更稳健的图片URL提取）
在 V1 基础上增强：
1) 候选图片URL更全面：img/source + a[href] + background-image + data-srcset 等
2) requests 增加 headers + 简单重试
3) 兼容 _eCom / 非_eCom 命名；兼容 png/webp/jpg/jpeg
4) 保留原有 pipeline 入口函数与参数（main / download_images_by_code_file）
"""

import time
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# === 你的项目内配置 ===
from config import ECCO, ensure_all_dirs

# ---------------- 基本配置 ----------------
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = ECCO["IMAGE_DOWNLOAD"]
WAIT = 0
DELAY = 0
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5

ensure_all_dirs(IMAGE_DIR)

# ============== WebDriver（稳）=============
try:
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    ChromeDriverManager = None
    Service = None


def create_driver():
    opts = Options()
    for a in ["--headless=new", "--disable-gpu", "--no-sandbox",
              "--disable-dev-shm-usage", "--window-size=1920x1080"]:
        opts.add_argument(a)

    try:
        return webdriver.Chrome(options=opts)
    except Exception as e:
        print(f"[WARN] Selenium Manager 启动失败：{e}")

    if ChromeDriverManager and Service:
        driver_path = ChromeDriverManager().install()
        return webdriver.Chrome(service=Service(driver_path), options=opts)

    raise RuntimeError("无法创建 Chrome WebDriver。请安装 selenium>=4.6；必要时安装 webdriver-manager。")


# ============== 工具函数：srcset 解析/命名规范 ==============
_VIEW_TOKEN = r"(?:o|m|b|s|top_left_pair|front_pair)"
_EXT_TOKEN  = r"(?:png|webp|jpg|jpeg)"


def _strip_query(url: str) -> str:
    u = urlparse(url)
    return urlunparse(u._replace(query=""))


def _pick_largest_from_srcset(srcset: str) -> str | None:
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
            except Exception:
                w = 0
        if w > best_w:
            best_url, best_w = url, w
    return best_url


def _extract_urls_from_style(style_text: str):
    """
    从 style="background-image: url(...)" 抽取 URL
    """
    if not style_text:
        return
    # 支持 url("...") / url('...') / url(...)
    for m in re.finditer(r'url\((?P<q>[\'"]?)(?P<u>.+?)(?P=q)\)', style_text, flags=re.I):
        u = m.group("u").strip()
        if u:
            yield u


def _fix_url(u: str) -> str | None:
    """补全协议、过滤空值"""
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if u.startswith("//"):
        return "https:" + u
    return u


def _looks_like_image_url(u: str) -> bool:
    """只接受图片链接（含查询参数也行）"""
    if not u:
        return False
    lu = u.lower()
    return any(ext in lu for ext in (".png", ".webp", ".jpg", ".jpeg"))


def _iter_image_candidate_urls(soup: BeautifulSoup):
    """
    遍历页面中可能的商品图 URL，优先取 srcset 的最大尺寸。
    V2增强：兼容 data-srcset、a[href] 图片直链、协议省略 //cdn...
    """
    # ---------- <img> ----------
    for img in soup.find_all("img"):
        # srcset / data-srcset 优先取最大
        for k in ("srcset", "data-srcset"):
            srcset = img.get(k)
            if srcset:
                best = _pick_largest_from_srcset(srcset)
                best = _fix_url(best)
                if best and _looks_like_image_url(best):
                    yield best

        # src / data-src / data-original
        for k in ("src", "data-src", "data-original"):
            u = _fix_url(img.get(k))
            if u and _looks_like_image_url(u):
                yield u

    # ---------- <source> ----------
    for tag in soup.find_all("source"):
        for k in ("srcset", "data-srcset"):
            srcset = tag.get(k)
            if srcset:
                best = _pick_largest_from_srcset(srcset)
                best = _fix_url(best)
                if best and _looks_like_image_url(best):
                    yield best

    # ✅ ---------- <a href>（新版 eCom 经常在这里） ----------
    for a in soup.find_all("a"):
        href = _fix_url(a.get("href"))
        if href and _looks_like_image_url(href):
            yield href



def _parse_code_view_from_filename(url: str) -> tuple[str | None, str | None, str | None, str]:
    """
    从 URL 文件名解析 (style6, color5, view, ext)
    兼容：
    - 470824-51866-m_eCom.png
    - 470824-51866-m.png
    - 470824-51866-top_left_pair_eCom.webp
    - 470824-51866-top_left_pair.webp
    - 470824-51866-o.jpg
    """
    no_q = _strip_query(url).lower()
    path = urlparse(no_q).path
    fname = Path(path).name

    # 1) -<view>_ecom.<ext>
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

    return None, None, None, Path(path).suffix.lower()


def _normalize_save_name(url: str, fallback_code: str | None) -> tuple[str, str]:
    """
    生成保存名 (basename, ext)：
    - 优先 6+5+view  -> 83541402308_m
    - 次选 6+5       -> 83541402308
    - 再 fallback_code-> 83541402308
    - 再兜底用 stem
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
    m = re.search(r'/(\d{6})/(\d{5})(?:[/?#]|$)', u)
    if m:
        return m.group(1) + m.group(2)
    return None


def _extract_code_from_images_html(html: str) -> str | None:
    m = re.search(r'/(\d{6})-(\d{5})-(?:' + _VIEW_TOKEN + r')\.(?:' + _EXT_TOKEN + r')', html, flags=re.I)
    if m:
        return m.group(1) + m.group(2)
    m2 = re.search(r'/(\d{6})-(\d{5})\.(?:' + _EXT_TOKEN + r')', html, flags=re.I)
    if m2:
        return m2.group(1) + m2.group(2)
    m3 = re.search(r'/(\d{6})-(\d{5})', html, flags=re.I)
    if m3:
        return m3.group(1) + m3.group(2)
    return None


# ---------- 下载：headers + 重试 ----------
_SESSION = requests.Session()
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://gb.ecco.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _download_bytes(url: str, timeout=25, retries=2) -> bytes | None:
    last_err = None
    for i in range(retries + 1):
        try:
            resp = _SESSION.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(0.6 * (i + 1))
    print(f"❌ 下载失败(重试后仍失败): {url} - {last_err}")
    return None


def download_images_from_soup(soup: BeautifulSoup, formatted_code: str | None):
    """
    扫描页面的商品图片并下载：
    - 优先取 srcset 最大尺寸
    - 规范命名（6位款号+5位色号+视角）
    - 去重（basename 去重）
    """
    seen_basenames = set()

    for raw_url in _iter_image_candidate_urls_v2(soup):
        if not raw_url:
            continue

        lower_url = raw_url.lower()

        # 只接受图片资源（URL 中带扩展名）
        if not any(ext in lower_url for ext in (".png", ".webp", ".jpg", ".jpeg")):
            continue

        basename, ext = _normalize_save_name(raw_url, formatted_code)

        # 如果解析不到 view，且 fallback_code 一样，会导致所有图同名被去重。
        # V2 做一个保护：当 basename == formatted_code 且没有 view 时，允许继续下载，
        # 但用 URL stem 做 suffix，避免只下载一张图。
        if formatted_code and basename == formatted_code:
            # 从文件名 stem 提取一个可区分的后缀（例如 m_ecom / o / top_left_pair）
            stem = Path(urlparse(_strip_query(raw_url)).path).stem.lower()
            # stem 可能是 "835414-02308-m_ecom" -> 取最后一段
            parts = re.split(r"[-_]", stem)
            if parts:
                tail = parts[-1]
                # 避免 tail 还是数字
                if not re.fullmatch(r"\d+", tail):
                    basename = f"{basename}_{tail}"

        if basename in seen_basenames:
            continue
        seen_basenames.add(basename)

        save_path = IMAGE_DIR / f"{basename}{ext}"
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 跳过: {save_path.name}")
            continue

        data = _download_bytes(raw_url)
        if not data:
            continue

        save_path.write_bytes(data)
        print(f"🖼️ 下载: {save_path.name}")
        time.sleep(DELAY)


def process_image_url(url):
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)

        real_url = driver.current_url or url
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        formatted_code = None

        # 旧站点：DOM 里可能直接有 11 位
        code_info = soup.find('div', class_='product_info__product-number')
        if code_info:
            text = code_info.text.strip()
            digits = re.search(r'(\d{11})', text)
            if digits:
                formatted_code = digits.group(1)

        # 新站点：URL 里 6+5
        if not formatted_code:
            formatted_code = _extract_code_from_url(real_url)

        # 回退：从 HTML 的图片文件名提取 6+5
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


if __name__ == "__main__":
    # main()  # 正常：按 product_links.txt 批量下载
    code_txt_path = ECCO["BASE"] / "publication" / "补图编码.txt"
    download_images_by_code_file(code_txt_path)
