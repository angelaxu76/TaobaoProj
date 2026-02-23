# -*- coding: utf-8 -*-
"""
Marks & Spencer 商品图片下载

- 从 links_jacket.txt / links_lingerie.txt 读取商品链接
- 解析 __NEXT_DATA__ 提取图片 URL（兼容新旧两种 M&S 页面结构）
- 多线程并发下载，跳过已存在图片
- 支持按商品编码从数据库查询 URL 补图
"""

import re
import json
import requests
import psycopg2
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MARKSANDSPENCER, ensure_all_dirs
from psycopg2.extras import RealDictCursor

# === 配置 ===
LINKS_FILE_JACKET   = MARKSANDSPENCER["LINKS_FILE_JACKET"]
LINKS_FILE_LINGERIE = MARKSANDSPENCER["LINKS_FILE_LINGERIE"]
IMAGE_DIR           = MARKSANDSPENCER["IMAGE_DOWNLOAD"]
TABLE_NAME          = MARKSANDSPENCER["TABLE_NAME"]
PGSQL_CONFIG        = MARKSANDSPENCER["PGSQL_CONFIG"]

# M&S 图片 CDN 模板：assetId → 完整 URL
MS_IMAGE_CDN = "https://asset1.cxnmarksandspencer.com/is/image/mands/{}?$PDP_M_ZOOM$&fmt=webp&wid=1008"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
MAX_WORKERS         = 5
SKIP_EXISTING_IMAGE = True

ensure_all_dirs(IMAGE_DIR)


# ===================== 工具函数 =====================

def _load_json_safe(text: str):
    if not text:
        return None
    text = text.replace("undefined", "null")
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_color_code(color: str) -> str:
    """去掉非字母数字字符并转大写，与 fetch_jacket_info.py 保持一致。"""
    if not color:
        return ""
    return re.sub(r"[^A-Za-z0-9]+", "", color).upper()


def extract_product_code(url: str, next_data: dict | None) -> str:
    """
    提取商品编码。
    优先从 __NEXT_DATA__ 取 strokeId / productExternalId；
    其次从 URL 路径 /p/<code> 提取；
    最后附加颜色后缀（?color=XXX）。
    """
    code = None

    if next_data:
        page_props = (next_data.get("props") or {}).get("pageProps") or {}

        # 新结构：productDetails
        pd = page_props.get("productDetails")
        if isinstance(pd, dict):
            attrs = pd.get("attributes") or {}
            code = attrs.get("strokeId") or pd.get("productExternalId") or pd.get("id")

        # 旧结构：productSheet
        if not code:
            sheet = page_props.get("productSheet")
            if isinstance(sheet, dict):
                code = sheet.get("code") or sheet.get("id")

    # 从 URL 路径兜底
    if not code:
        m = re.search(r"/p/(\w+)", url)
        if m:
            code = m.group(1)

    code = str(code) if code else "unknown"

    # 附加颜色后缀
    qs = parse_qs(urlparse(url).query)
    color_raw = (qs.get("color") or [None])[0]
    if color_raw:
        code = f"{code}_{_normalize_color_code(color_raw)}"

    return code


def extract_image_urls(next_data: dict | None, url: str) -> list[str]:
    """
    从 __NEXT_DATA__ 提取 M&S 商品图片 URL。

    M&S 图片实际存储为 assetId，位于：
        productDetails.variants[n].assets[].assetId

    通过 CDN 模板拼接成真实 URL。
    颜色匹配：优先取 URL ?color= 对应的 variant；
    若未匹配则退为第一个 variant。

    兜底兼容旧结构（productSheet.multiMedia / imageUrls）。
    """
    if not next_data:
        return []

    page_props = (next_data.get("props") or {}).get("pageProps") or {}

    # --- 当前颜色（从 URL 读取） ---
    color_from_url = (parse_qs(urlparse(url).query).get("color") or [None])[0]
    color_norm = _normalize_color_code(color_from_url) if color_from_url else ""

    # --- 新结构：productDetails.variants[].assets[] ---
    pd = page_props.get("productDetails")
    if isinstance(pd, dict):
        variants = pd.get("variants") or []

        # 匹配颜色对应的 variant
        matched_variant = None
        if color_norm:
            for v in variants:
                vc = _normalize_color_code(v.get("colour") or v.get("color") or "")
                if vc == color_norm:
                    matched_variant = v
                    break

        # 未命中则取第一个
        if matched_variant is None and variants:
            matched_variant = variants[0]

        if matched_variant:
            asset_ids = [
                a["assetId"]
                for a in (matched_variant.get("assets") or [])
                if a.get("assetId")
            ]
            if asset_ids:
                return [MS_IMAGE_CDN.format(aid) for aid in asset_ids]

    # --- 旧结构：productSheet ---
    sheet = page_props.get("productSheet")
    if isinstance(sheet, dict):
        raw: list[str] = []

        for mm in (sheet.get("multiMedia") or []):
            for key in ("src", "url", "href", "imageUrl"):
                v = mm.get(key)
                if v and isinstance(v, str):
                    raw.append(v)
                    break

        for u in (sheet.get("imageUrls") or []):
            if isinstance(u, str):
                raw.append(u)

        seen: set[str] = set()
        result: list[str] = []
        for u in raw:
            u = u.strip()
            if u and u not in seen:
                seen.add(u)
                result.append(u)
        return result

    return []


# ===================== 下载逻辑 =====================

def download_image(url: str, save_path: Path):
    try:
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 已存在，跳过: {save_path.name}")
            return
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            save_path.write_bytes(r.content)
            print(f"🖼️ 下载成功: {save_path.name}")
        else:
            print(f"⚠️ 图片请求失败（{r.status_code}）: {url}")
    except Exception as e:
        print(f"❌ 下载失败: {url} → {e}")


def process_product_url(url: str):
    print(f"📷 处理商品: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        script_tag = soup.find("script", id="__NEXT_DATA__")
        next_data = _load_json_safe(script_tag.string) if script_tag else None

        code       = extract_product_code(url, next_data)
        image_urls = extract_image_urls(next_data, url)

        if not image_urls:
            print(f"⚠️ 未找到图片: {url}")
            return

        for idx, img_url in enumerate(image_urls, 1):
            # CDN URL 含 fmt=webp 参数，扩展名统一用 .webp
            img_path = IMAGE_DIR / f"{code}_{idx}.webp"
            download_image(img_url, img_path)

    except Exception as e:
        print(f"❌ 商品处理失败: {url} → {e}")


def _run_batch(urls: list[str]):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_product_url, url) for url in urls]
        for future in as_completed(futures):
            future.result()


# ===================== 公开入口 =====================

def download_jacket_images():
    """下载 links_jacket.txt 中所有商品的图片。"""
    if not LINKS_FILE_JACKET.exists():
        print(f"❌ 链接文件不存在: {LINKS_FILE_JACKET}")
        return
    urls = [u.strip() for u in LINKS_FILE_JACKET.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"📦 共 {len(urls)} 个外套商品图片待下载")
    _run_batch(urls)
    print("\n✅ 外套图片下载完成")


def download_lingerie_images():
    """下载 links_lingerie.txt 中所有商品的图片。"""
    if not LINKS_FILE_LINGERIE.exists():
        print(f"❌ 链接文件不存在: {LINKS_FILE_LINGERIE}")
        return
    urls = [u.strip() for u in LINKS_FILE_LINGERIE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"📦 共 {len(urls)} 个内衣商品图片待下载")
    _run_batch(urls)
    print("\n✅ 内衣图片下载完成")


# ===================== 补图（按编码从数据库查 URL） =====================

def fetch_urls_from_db_by_codes(code_file_path, pgsql_config, table_name):
    code_list = [
        line.strip()
        for line in Path(code_file_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"🔍 共读取到 {len(code_list)} 个商品编码")

    urls: set[str] = set()
    try:
        conn   = psycopg2.connect(**pgsql_config)
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
    """按编码文件从数据库查询 URL 并补图。"""
    urls = fetch_urls_from_db_by_codes(code_txt_path, PGSQL_CONFIG, TABLE_NAME)
    print(f"📦 共需下载 {len(urls)} 个商品的图片\n")
    _run_batch(urls)
    print("\n✅ 所有指定商品图片下载完成")


# ===================== 主入口 =====================

def main():
    download_jacket_images()
    download_lingerie_images()


if __name__ == "__main__":
    main()
