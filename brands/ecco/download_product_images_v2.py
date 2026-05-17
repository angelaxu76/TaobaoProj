# -*- coding: utf-8 -*-
"""
ECCO 商品图片下载 V2（编码过滤 + 防坏图 + 兼容新旧 eCom）
基于你现有脚本升级：:contentReference[oaicite:1]{index=1}

核心特性：
1) 编码过滤：只下载 URL path 中包含 6-5 或 11 位编码的图片（避免推荐区混入）
2) 兼容新旧命名：-view_eCom.ext / -view.ext / png/webp/jpg/jpeg
3) 防坏图：校验 Content-Type 为 image/* + magic bytes（png/jpg/webp）
4) 同视角去重：按 view 去重，同视角优先 eCom，其次优先 width 更大的链接
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
from config import ECCO, ensure_all_dirs, GLOBAL_CHROMEDRIVER_PATH
from selenium.webdriver.chrome.service import Service

# ---------------- 基本配置 ----------------
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = ECCO["IMAGE_DOWNLOAD"]
WAIT = 0
DELAY = 0
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5

ensure_all_dirs(IMAGE_DIR)

# ============== WebDriver ==============
def create_driver():
    opts = Options()
    for a in ["--headless=new", "--disable-gpu", "--no-sandbox",
              "--disable-dev-shm-usage", "--window-size=1920x1080"]:
        opts.add_argument(a)
    return webdriver.Chrome(service=Service(GLOBAL_CHROMEDRIVER_PATH), options=opts)


# ============== 工具函数：srcset / 解析 / 过滤 ==============
_VIEW_TOKEN = r"(?:o|m|b|s|top_left_pair|front_pair)"
_EXT_TOKEN  = r"(?:png|webp|jpg|jpeg)"


def _strip_query(url: str) -> str:
    u = urlparse(url)
    return urlunparse(u._replace(query=""))


def _fix_url(u: str) -> str | None:
    if not u:
        return None
    u = u.strip().replace("\n", "").replace("\r", "")
    if not u:
        return None
    if u.startswith("//"):
        return "https:" + u
    return u



def _looks_like_image_url(u: str) -> bool:
    if not u:
        return False
    lu = u.lower()
    return any(ext in lu for ext in (".png", ".webp", ".jpg", ".jpeg"))


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


def _iter_image_candidate_urls(soup: BeautifulSoup):
    """
    候选图片 URL：
    - img[src/srcset/data-src/data-original/data-srcset]
    - source[srcset/data-srcset]
    - a[href]（新站 eCom 图片直链常在这里）
    """
    # <img>
    for img in soup.find_all("img"):
        for k in ("srcset", "data-srcset"):
            srcset = img.get(k)
            if srcset:
                best = _pick_largest_from_srcset(srcset)
                best = _fix_url(best)
                if best and _looks_like_image_url(best):
                    yield best

        for k in ("src", "data-src", "data-original"):
            u = _fix_url(img.get(k))
            if u and _looks_like_image_url(u):
                yield u

    # <source>
    for tag in soup.find_all("source"):
        for k in ("srcset", "data-srcset"):
            srcset = tag.get(k)
            if srcset:
                best = _pick_largest_from_srcset(srcset)
                best = _fix_url(best)
                if best and _looks_like_image_url(best):
                    yield best

    # <a href>
    for a in soup.find_all("a"):
        href = _fix_url(a.get("href"))
        if href and _looks_like_image_url(href):
            yield href


def _parse_code_view_from_filename(url: str) -> tuple[str | None, str | None, str | None, str]:
    """
    从 URL 文件名解析 (style6, color5, view, ext)
    兼容：
    - 835414-02308-m_eCom.png
    - 835414-02308-m.png
    - 835414-02308-top_left_pair_eCom.webp
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


def _normalize_save_name(url: str, fallback_code: str | None) -> str:
    """
    生成 basename（不含扩展名）
    - 优先 6+5+view -> 83541402308_m
    - 次选 6+5     -> 83541402308
    - 再 fallback  -> 83541402308
    - 兜底 stem
    """
    style6, color5, view, _ = _parse_code_view_from_filename(url)
    if style6 and color5 and view:
        return f"{style6}{color5}_{view}"
    if style6 and color5:
        return f"{style6}{color5}"
    if fallback_code:
        return fallback_code

    stem = Path(urlparse(_strip_query(url)).path).stem
    return stem.replace("-", "_")


def _extract_code_from_url(u: str) -> str | None:
    """从 URL /product/.../<6位>/<5位> 提取 11 位编码"""
    m = re.search(r'/(\d{6})/(\d{5})(?:[/?#]|$)', u)
    if m:
        return m.group(1) + m.group(2)
    return None


def _extract_code_from_images_html(html: str) -> str | None:
    """从页面 HTML 的图片文件名提取编码（回退）"""
    m = re.search(r'(\d{6})-(\d{5})', html, flags=re.I)
    if m:
        return m.group(1) + m.group(2)
    m2 = re.search(r'(\d{11})', html)
    if m2:
        return m2.group(1)
    return None


def _code_patterns(formatted_code: str) -> tuple[str, str]:
    """
    11位编码 83541402308 -> ("835414-02308", "83541402308")
    """
    if not formatted_code or len(formatted_code) != 11:
        return ("", "")
    dashed = formatted_code[:6] + "-" + formatted_code[6:]
    return dashed, formatted_code


def _url_contains_code(url: str, formatted_code: str | None) -> bool:
    """
    编码过滤：图片 URL（去掉 query）必须包含 835414-02308 或 83541402308
    如果拿不到 formatted_code，就不强行过滤（避免漏图）
    """
    if not formatted_code or len(formatted_code) != 11:
        return True
    dashed, plain = _code_patterns(formatted_code)
    path = urlparse(_strip_query(url)).path.lower()
    return (dashed.lower() in path) or (plain.lower() in path)


def _get_width_param(url: str) -> int:
    """从 query 里提取 width 参数用于选大图（没有就 0）"""
    qs = (urlparse(url).query or "").lower()
    m = re.search(r"(?:^|&)(?:width|w)=(\d+)(?:&|$)", qs)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    return 0


def _is_ecom_url(url: str) -> bool:
    """判断是否 eCom 版本链接"""
    p = _strip_query(url).lower()
    return "_ecom" in p


# ============== requests 下载（防坏图） ==============
_SESSION = requests.Session()
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://gb.ecco.com/",
    "Accept": "image/png,image/webp,image/jpeg,image/*,*/*;q=0.8",
}


def _detect_image_ext(data: bytes) -> str | None:
    if not data or len(data) < 16:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    # AVIF/HEIF: ....ftypavif / ftypheic / ftypmif1 等
    if b"ftypavif" in data[:64] or b"ftypheic" in data[:64] or b"ftypmif1" in data[:64]:
        return ".avif"
    return None



def _download_bytes(url: str, timeout=25, retries=2) -> tuple[bytes | None, str | None]:
    """
    返回 (data, real_ext)：
    - data 为图片二进制；失败返回 (None, None)
    - real_ext 通过 magic bytes 判断 .png/.jpg/.webp
    """
    last_err = None
    for i in range(retries + 1):
        try:
            url = _force_image_format(url, "png")
            resp = _SESSION.get(url, headers=_DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)

            ct = (resp.headers.get("Content-Type") or "").lower()
            data = resp.content or b""

            if not ct.startswith("image/"):
                raise RuntimeError(f"Not image content-type: {ct}")

            real_ext = _detect_image_ext(data)
            if not real_ext:
                raise RuntimeError("Invalid image magic bytes")

            return data, real_ext

        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(0.6 * (i + 1))

    print(f"❌ 下载失败(重试后仍失败): {url} - {last_err}")
    return None, None


# ============== 下载主逻辑（编码过滤 + 选大图 + eCom 优先） ==============
def download_images_from_soup(soup: BeautifulSoup, formatted_code: str | None):
    """
    - 先用编码过滤：只要 URL path 不包含该编码，就跳过
    - 再按 view 去重：同视角只保留一个
      - 优先 eCom
      - eCom 相同优先级下，选 width 更大的
    - 最后才下载并保存（并校验是真图片）
    """
    # view_key -> (priority, width, url)
    # priority: eCom=2, normal=1
    best_by_view: dict[str, tuple[int, int, str]] = {}

    for raw in _iter_image_candidate_urls(soup):
        if not raw:
            continue

        raw_url = _fix_url(raw)
        if not raw_url:
            continue
        if not _looks_like_image_url(raw_url):
            continue

        # ✅ 编码过滤（最关键）
        if not _url_contains_code(raw_url, formatted_code):
            continue

        style6, color5, view, _ = _parse_code_view_from_filename(raw_url)
        view_key = view or "unknown"

        pri = 2 if _is_ecom_url(raw_url) else 1
        w = _get_width_param(raw_url)

        if view_key not in best_by_view:
            best_by_view[view_key] = (pri, w, raw_url)
        else:
            old_pri, old_w, _old_url = best_by_view[view_key]
            # eCom 优先；同优先级取 width 更大
            if pri > old_pri or (pri == old_pri and w > old_w):
                best_by_view[view_key] = (pri, w, raw_url)

    # 依次下载最佳 URL
    for view_key, (_pri, _w, url) in best_by_view.items():
        basename = _normalize_save_name(url, formatted_code)

        # unknown 兜底避免覆盖
        if view_key == "unknown" and formatted_code:
            basename = f"{formatted_code}_unknown"

        data, real_ext = _download_bytes(url)
        if not data:
            continue

        save_path = IMAGE_DIR / f"{basename}{real_ext}"
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 跳过: {save_path.name}")
            continue

        save_path.write_bytes(data)
        print(f"🖼️ 下载: {save_path.name}")
        time.sleep(DELAY)


# ============== 单页处理：保持原函数名与参数 ==============
def process_image_url(url: str):
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)

        real_url = driver.current_url or url
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        formatted_code = None

        # 旧站点 DOM（如果存在 11 位编码）
        code_info = soup.find('div', class_='product_info__product-number')
        if code_info:
            text = (code_info.text or "").strip()
            m = re.search(r'(\d{11})', text)
            if m:
                formatted_code = m.group(1)

        # 新站点：从 URL 提取 6+5
        if not formatted_code:
            formatted_code = _extract_code_from_url(real_url)

        # 回退：从页面图片文件名提取
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


from urllib.parse import urlencode, parse_qsl

def _force_image_format(url: str, fmt: str = "png") -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    q["format"] = fmt  # 强制 png
    new_q = urlencode(q, doseq=True)
    return urlunparse(u._replace(query=new_q))


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

    # 补图模式：按编码文件
    code_txt_path = ECCO["BASE"] / "publication" / "补图编码.txt"
    download_images_by_code_file(code_txt_path)
