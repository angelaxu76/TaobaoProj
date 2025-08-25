from __future__ import annotations
import json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup

# === 项目内路径/配置 ===
# 你之前已经在 config 里加了 REISS 配置，这里直接引用
try:
    from config import REISS  # 包含 TXT_DIR / LINKS_FILE / BRAND / ...
except ImportError:
    # 允许独立运行（可手工传参）
    REISS = None

# === 文本写入：沿用你上传的 writer，输出完全兼容 parse_txt / parse_barbour_jingya 等 ===
from txt_writer import format_txt

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9,zh-CN;q=0.8"}

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _money_to_float(text: Optional[str]) -> float:
    if not text:
        return 0.0
    t = text.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else 0.0

def _fetch_html(url: str, retry: int = 3, timeout: int = 25) -> str:
    last_exc = None
    for i in range(retry):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.text
        except Exception as e:
            last_exc = e
        time.sleep(1.2)
    raise RuntimeError(f"GET {url} failed: {last_exc or 'HTTP '+str(r.status_code)}")

def _product_code_from_url(url: str) -> Optional[str]:
    # /style/su583537/ap8544 -> ap8544 -> AP8-544
    m = re.search(r"/style/[a-z0-9\-]+/([a-z0-9]{6,8})", url, flags=re.I)
    if not m:
        return None
    pid = m.group(1).upper()
    if len(pid) >= 4:
        return f"{pid[:3]}-{pid[3:]}"
    return pid

def _parse_next_data(soup: BeautifulSoup) -> Optional[Dict]:
    tag = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if not tag:
        return None
    data = json.loads(tag.string or "{}")
    q = (((data.get("props") or {}).get("pageProps") or {})
         .get("dehydratedState") or {}).get("queries") or []
    # 找到 queryKey = ["product", "<pid>"] 的项
    for item in q:
        state = item.get("state") or {}
        key = item.get("queryKey")
        if isinstance(key, list) and key and key[0] == "product":
            if isinstance(state.get("data"), dict):
                return state["data"]
    return None

def _parse_dom_prices(soup: BeautifulSoup) -> Tuple[float, float]:
    was_el = soup.select_one('[data-testid="product-was-price"]')
    now_el = soup.select_one('[data-testid="product-now-price"] span')
    original = _money_to_float(was_el.get_text(strip=True) if was_el else "")
    discount = _money_to_float(now_el.get_text(strip=True) if now_el else "")
    if original == 0.0 and discount > 0.0:
        original = discount  # 非折扣场景只有一个价
    return original, discount

def _parse_dom_color(soup: BeautifulSoup) -> str:
    el = soup.select_one('span[data-testid="selected-colour-label"]')
    return _clean_text(el.get_text()) if el else ""

def _parse_dom_desc_features(soup: BeautifulSoup) -> Tuple[str, str]:
    # 描述
    desc_el = soup.select_one('p[data-testid="item-description"]')
    description = _clean_text(desc_el.get_text()) if desc_el else ""
    # 特性点
    feats = [ _clean_text(li.get_text())
              for li in soup.select('li[data-translate-id="tov-bullet"]') ]
    feature_str = " | ".join([f for f in feats if f]) if feats else ""
    return description, feature_str

def _parse_dom_sizes_fallback(soup: BeautifulSoup) -> Dict[str, str]:
    # 兜底：用按钮 aria-label 提取（"16 unavailable" / "10 available"...）
    size_map = {}
    for b in soup.select('[data-testid="size-chips-button-group"] button[aria-label]'):
        size_txt = _clean_text(b.get_text())
        size = size_txt or re.sub(r"[^\d\.A-Za-z/]", "", b.get("aria-label","").split()[0])
        label = (b.get("aria-label") or "").lower()
        status = "无货" if "unavailable" in label else "有货"
        if size:
            size_map[size] = status
    return size_map

def _parse_name_from_title(soup: BeautifulSoup) -> str:
    t = (soup.title.string or "") if soup.title else ""
    t = t.replace(" - REISS", "")
    t = re.sub(r"^\s*Reiss\s+", "", t, flags=re.I)  # 去掉前缀品牌
    return _clean_text(t)

def parse_reiss_product(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    # 1) 优先从 __NEXT_DATA__ 拿结构化数据（有 gender / category / sizes 等）
    next_data = _parse_next_data(soup)

    # 2) 名称/颜色/描述/特性（DOM）
    product_title = _parse_name_from_title(soup)
    color = _parse_dom_color(soup)
    description, feature_str = _parse_dom_desc_features(soup)

    # 3) 编码（先 DOM，后 URL 兜底）
    product_code = ""
    code_label = soup.find(string=re.compile(r"Product Code", re.I))
    if code_label:
        code_span = (code_label.find_parent().find_next("span")
                     if hasattr(code_label, "find_parent") else None)
        if code_span:
            product_code = _clean_text(code_span.get_text())
    if not product_code:
        pc = _product_code_from_url(url)
        if pc:
            product_code = pc

    # 4) 价格（DOM；必要时用 JSON sizes 的统一价兜底）
    original, discount = _parse_dom_prices(soup)
    if next_data and discount == 0.0:
        # 部分页面没有展示折后价，用 options 里的 priceUnformatted
        try:
            opts = (next_data.get("options") or {}).get("options") or []
            if opts:
                discount = float(opts[0].get("priceUnformatted") or 0) or discount
                if original == 0.0:
                    original = discount
        except Exception:
            pass

    # 5) 性别 / 类别
    gender = ""
    style_category = ""
    if next_data:
        gender = (next_data.get("gender") or "").strip()  # e.g. "Women" / "Men"
        style_category = (next_data.get("category") or "").strip()

    # 6) 尺码与库存
    size_map: Dict[str, str] = {}
    size_detail: Dict[str, Dict] = {}

    if next_data:
        try:
            for o in (next_data.get("options") or {}).get("options", []):
                name = str(o.get("name") or "").strip()  # 显示尺码（如 "10"）
                st = (o.get("stockStatus") or "").lower()
                status = "有货" if st in ("instock", "lowstock") else "无货"
                if name:
                    size_map[name] = status
                    # Reiss 这边没有明确库存数/EAN，这里只留空结构，兼容 txt_parser
                    size_detail[name] = {"stock_count": 0, "ean": ""}
        except Exception:
            pass

    if not size_map:
        size_map = _parse_dom_sizes_fallback(soup)

    # 7) 特性/描述兜底（若为空用简短组合）
    if not description and feature_str:
        description = feature_str
    if not feature_str and description:
        # 把描述首句当特性简述
        feature_str = description.split(".")[0].strip()

    # 8) 组织写入字段（完全贴合 txt_writer 的键）
    info = {
        "Product Code": product_code or "UNKNOWN",
        "Product Name": product_title or "No Name",
        "Product Description": description or "No Data",
        "Product Gender": gender,                     # 可为空
        "Product Color": color,                       # 可为空
        "Product Price": str(original or 0),
        "Adjusted Price": str(discount or original or 0),
        "Product Material": "No Data",
        "Style Category": style_category,             # 可为空（例如 Dresses）
        "Feature": feature_str or "No Data",
        "SizeMap": size_map,                          # e.g. {"10":"有货","16":"无货"}
        "SizeDetail": size_detail,                    # 结构保留，值缺省
        "Source URL": url
    }
    return info

# === 公共入口 ===

def fetch_one_and_write(url: str, save_dir: Path, brand: str = "reiss") -> Tuple[str, bool, str]:
    try:
        html = _fetch_html(url)
        info = parse_reiss_product(html, url)

        # 文件名优先用 Product Code；退化用 URL 尾段
        fname = info["Product Code"].replace("/", "_")
        if not fname or fname == "UNKNOWN":
            fname = (_product_code_from_url(url) or re.sub(r"\W+", "_", url))[:80]
        path = Path(save_dir) / f"{fname}.txt"

        format_txt(info, path, brand=brand)
        print(f"✅ TXT 写入: {path.name}")
        return url, True, ""
    except Exception as e:
        # 页失败也不影响其它 URL，且尽量输出一个最小 TXT（只含 URL + 占位）
        try:
            print(f"💥 解析失败（继续）：{url} -> {e}")
            minimal = {
                "Product Code": _product_code_from_url(url) or "UNKNOWN",
                "Product Name": "No Name",
                "Product Description": "No Data",
                "Product Gender": "",
                "Product Color": "",
                "Product Price": "0",
                "Adjusted Price": "0",
                "Product Material": "No Data",
                "Style Category": "",
                "Feature": "No Data",
                "SizeMap": {},          # 为空则 parse_generic 不会入库，留待复抓
                "SizeDetail": {},
                "Source URL": url
            }
            # 即使失败也尽量留一份记录
            fallback_name = minimal["Product Code"] or "UNKNOWN"
            path = Path(save_dir) / f"{fallback_name}.txt"
            format_txt(minimal, path, brand=brand)
            print(f"↳ 已写入最小 TXT（供追踪）: {path.name}")
        except Exception as ee:
            print(f"‼️ 最小 TXT 写入也失败：{ee}")
        return url, False, str(e)

def reiss_fetch_all(
    urls_file: Optional[Path] = None,
    save_dir: Optional[Path] = None,
    max_workers: int = 8
):
    if REISS:
        urls_file = urls_file or REISS["LINKS_FILE"]
        save_dir = save_dir or REISS["TXT_DIR"]
    if not urls_file or not save_dir:
        raise ValueError("缺少 urls_file / save_dir，请传入或在 config 中配置 REISS。")

    Path(save_dir).mkdir(parents=True, exist_ok=True)

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip()]

    ok = fail = 0
    errs: List[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(fetch_one_and_write, u, Path(save_dir), "reiss") for u in urls]
        for fut in as_completed(futs):
            _, success, msg = fut.result()
            ok += 1 if success else 0
            fail += 0 if success else 1
            if not success:
                errs.append(msg)

    print(f"🎯 完成：成功 {ok}，失败 {fail}，输出目录：{save_dir}")
    if fail:
        print("⚠️ 失败原因示例：", errs[:3])
