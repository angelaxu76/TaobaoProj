from __future__ import annotations
import json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup

# === 项目内路径/配置 ===
try:
    from config import REISS  # 包含 TXT_DIR / LINKS_FILE / BRAND / ...
except ImportError:
    REISS = None

# === 文本写入：沿用你的 writer ===
from common_taobao.ingest.txt_writer import format_txt

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9,zh-CN;q=0.8"}

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _money_to_float(text: Optional[str]) -> float:
    if not text:
        return 0.0
    t = text.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else 0.0

def _fetch_html(url: str, retry: int = 3, timeout: int = 25) -> str:
    last_exc = None
    for _ in range(retry):
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
        original = discount
    return original, discount

def _parse_dom_color(soup: BeautifulSoup) -> str:
    el = soup.select_one('span[data-testid="selected-colour-label"]')
    return _clean_text(el.get_text()) if el else ""

def _parse_dom_desc_features(soup: BeautifulSoup) -> Tuple[str, str]:
    desc_el = soup.select_one('p[data-testid="item-description"]')
    description = _clean_text(desc_el.get_text()) if desc_el else ""
    feats = [_clean_text(li.get_text())
             for li in soup.select('li[data-translate-id="tov-bullet"]')]
    feature_str = " | ".join([f for f in feats if f]) if feats else ""
    return description, feature_str

def _parse_dom_sizes_fallback(soup: BeautifulSoup) -> Dict[str, str]:
    size_map: Dict[str, str] = {}
    for b in soup.select('[data-testid="size-chips-button-group"] button[aria-label]'):
        size_txt = _clean_text(b.get_text())
        size = size_txt or re.sub(r"[^\d\.A-Za-z/]", "", (b.get("aria-label","").split() or [""])[0])
        label = (b.get("aria-label") or "").lower()
        status = "无货" if "unavailable" in label else "有货"
        if size:
            size_map[size] = status
    return size_map

def _parse_name_from_title(soup: BeautifulSoup) -> str:
    t = (soup.title.string or "") if soup.title else ""
    t = t.replace(" - REISS", "")
    t = re.sub(r"^\s*Reiss\s+", "", t, flags=re.I)
    return _clean_text(t)

# === 尺码规范化（仅格式化字母为 XS/S/M/L/XL，数字不变） ===
ALPHA_CANON_MAP = {
    "xx-small": "XXS", "xxs": "XXS", "x x small": "XXS",
    "x-small": "XS", "x small": "XS", "xsmall": "XS", "xs": "XS",
    "small": "S", "s": "S",
    "medium": "M", "m": "M",
    "large": "L", "l": "L",
    "x-large": "XL", "x large": "XL", "xlarge": "XL", "xl": "XL",
    "one size": "One Size", "onesize": "One Size", "os": "One Size",
}
ALPHA_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "One Size"]

def _normalize_alpha_sizes(size_map: Dict[str, str],
                           size_detail: Dict[str, Dict] | None = None
                           ) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    size_detail = size_detail or {}
    norm_map: Dict[str, str] = {}
    norm_detail: Dict[str, Dict] = {}

    def is_numeric(k: str) -> bool:
        return bool(re.fullmatch(r"\d{1,2}", k.strip()))

    for raw_key, status in size_map.items():
        k0 = (raw_key or "").strip()
        if not k0:
            continue
        if is_numeric(k0):
            key = k0
        else:
            k = k0.lower().replace("_", " ").replace("-", " ")
            k = re.sub(r"\s+", " ", k)
            key = ALPHA_CANON_MAP.get(k, k0)

        prev = norm_map.get(key, "无货")
        norm_map[key] = "有货" if ("有货" in (prev, status)) else "无货"
        norm_detail.setdefault(key, size_detail.get(raw_key, {"stock_count": 0, "ean": ""}))

    def sort_key(k: str):
        if k in ALPHA_ORDER:
            return (0, ALPHA_ORDER.index(k), 0)
        if k.isdigit():
            return (1, int(k), 0)
        return (2, 0, k)

    norm_map = dict(sorted(norm_map.items(), key=lambda x: sort_key(x[0])))
    norm_detail = {k: norm_detail[k] for k in norm_map.keys()}
    return norm_map, norm_detail

# === 新增：补齐 + 量化库存（不改抓取，只在写入前处理） ===
NUMERIC_RANGE = [str(x) for x in range(4, 22, 2)]  # 4,6,...,20
ALPHA_RANGE   = ["XS", "S", "M", "L", "XL"]

def _detect_size_schema(size_keys: List[str]) -> str:
    has_num   = any(k.isdigit() for k in size_keys)
    has_alpha = any(k in ALPHA_ORDER or k in ALPHA_RANGE for k in size_keys)
    if has_num and not has_alpha:
        return "numeric"
    if has_alpha and not has_num:
        return "alpha"
    if has_num and has_alpha:
        num_cnt = sum(1 for k in size_keys if k.isdigit())
        alp_cnt = sum(1 for k in size_keys if k in ALPHA_ORDER or k in ALPHA_RANGE)
        return "numeric" if num_cnt >= alp_cnt else "alpha"
    return "unknown"

def _fill_and_quantify_sizes(size_map: Dict[str, str],
                             size_detail: Dict[str, Dict]) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """
    - “有货” => stock_count = 3；“无货” => 0
    - 按 schema 补齐尺码范围（numeric: 4..22; alpha: XS..XL）
    - 否则（unknown/One Size等）不补齐，仅量化
    """
    keys = list(size_map.keys())
    schema = _detect_size_schema(keys)

    def quantize(status: str) -> int:
        return 3 if (status or "").strip() == "有货" else 0

    if schema == "numeric":
        full = NUMERIC_RANGE
    elif schema == "alpha":
        full = ALPHA_RANGE
    else:
        # 仅把已有的量化
        new_map = {}
        new_detail = {}
        for k, st in size_map.items():
            stock = quantize(st)
            new_map[k] = "有货" if stock > 0 else "无货"
            new_detail[k] = {"stock_count": stock,
                             "ean": size_detail.get(k, {}).get("ean", "0000000000000")}
        return new_map, new_detail

    new_map: Dict[str, str] = {}
    new_detail: Dict[str, Dict] = {}
    for s in full:
        st = size_map.get(s, "无货")
        stock = quantize(st)
        new_map[s] = "有货" if stock > 0 else "无货"
        new_detail[s] = {
            "stock_count": stock,
            "ean": size_detail.get(s, {}).get("ean", "0000000000000")
        }
    return new_map, new_detail
# === 补齐 + 量化结束 ===

def parse_reiss_product(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    next_data = _parse_next_data(soup)

    product_title = _parse_name_from_title(soup)
    color = _parse_dom_color(soup)
    description, feature_str = _parse_dom_desc_features(soup)

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

    original, discount = _parse_dom_prices(soup)
    if next_data and discount == 0.0:
        try:
            opts = (next_data.get("options") or {}).get("options") or []
            if opts:
                discount = float(opts[0].get("priceUnformatted") or 0) or discount
                if original == 0.0:
                    original = discount
        except Exception:
            pass

    gender = ""
    style_category = ""
    if next_data:
        gender = (next_data.get("gender") or "").strip()
        style_category = (next_data.get("category") or "").strip()

    size_map: Dict[str, str] = {}
    size_detail: Dict[str, Dict] = {}
    if next_data:
        try:
            for o in (next_data.get("options") or {}).get("options", []):
                name = str(o.get("name") or "").strip()
                st = (o.get("stockStatus") or "").lower()
                status = "有货" if st in ("instock", "lowstock") else "无货"
                if name:
                    size_map[name] = status
                    size_detail[name] = {"stock_count": 0, "ean": ""}
        except Exception:
            pass
    if not size_map:
        size_map = _parse_dom_sizes_fallback(soup)

    if not description and feature_str:
        description = feature_str
    if not feature_str and description:
        feature_str = description.split(".")[0].strip()

    # 1) 规范字母尺码
    if size_map:
        size_map, size_detail = _normalize_alpha_sizes(size_map, size_detail)
    # 2) 按规则补齐 + 量化库存（有货=3，无货=0）
    if size_map:
        size_map, size_detail = _fill_and_quantify_sizes(size_map, size_detail)

    info = {
        "Product Code": product_code or "UNKNOWN",
        "Product Name": product_title or "No Name",
        "Product Description": description or "No Data",
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": str(original or 0),
        "Adjusted Price": str(discount or original or 0),
        "Product Material": "No Data",
        "Style Category": style_category,
        "Feature": feature_str or "No Data",
        "SizeMap": size_map,          # 已补齐，状态“有货/无货”
        "SizeDetail": size_detail,    # 已量化：3/0，EAN 占位 "0000000000000"
        "Source URL": url
    }
    return info

# === 公共入口（名称/签名未改） ===
def fetch_one_and_write(url: str, save_dir: Path, brand: str = "reiss") -> Tuple[str, bool, str]:
    try:
        html = _fetch_html(url)
        info = parse_reiss_product(html, url)

        fname = info["Product Code"].replace("/", "_")
        if not fname or fname == "UNKNOWN":
            fname = (_product_code_from_url(url) or re.sub(r"\W+", "_", url))[:80]
        path = Path(save_dir) / f"{fname}.txt"

        format_txt(info, path, brand=brand)
        print(f"✅ TXT 写入: {path.name}")
        return url, True, ""
    except Exception as e:
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
                "SizeMap": {},
                "SizeDetail": {},
                "Source URL": url
            }
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
