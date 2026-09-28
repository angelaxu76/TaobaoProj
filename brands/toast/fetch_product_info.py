# -*- coding: utf-8 -*-
"""
TOAST 商品信息抓取 → TXT（沿用 common.ingest.txt_writer.format_txt 统一格式）

数据源：/products/{handle}.js
- 编码：tag style_colour（如 WTRVS27ECRU）
- 价格：便士 → 英镑；compare_at_price > price 时视为折扣（Product Price=原价，Adjusted Price=现价）
- 尺码：variant option2，available → 有货(DEFAULT_STOCK_COUNT) / 无货(0)，barcode 作为 EAN
- 性别：tag gender（Women/Men）优先，否则按 links_meta.json 里的所属类目推断
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from config import TOAST, DEFAULT_STOCK_COUNT
from common.ingest.txt_writer import format_txt
from brands.toast.shopify_api import (
    derive_product_code,
    fetch_product_js,
    handle_from_url,
    tag_value,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _pence_to_gbp(v) -> float:
    try:
        return round(int(v) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _load_meta(links_file: Path) -> Dict[str, dict]:
    p = Path(links_file).with_name("links_meta.json")
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ================= 描述解析 =================
def parse_description(html: str) -> Tuple[str, str, str]:
    """
    TOAST 描述结构：
        <p>介绍段落...</p> ... <p>短规格：Cotton denim. High waist. Regular fit.</p>
        <p>###</p>
        <h4>Details</h4><p>Machine wash 30ºC. 100% cotton. Made in Türkiye.</p>
        <h4>Size &amp; Fit</h4><p>Regular fit. ...</p>
    返回 (description, feature, material)
    """
    soup = BeautifulSoup(html or "", "html.parser")

    intro: List[str] = []
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for el in soup.find_all(["p", "h4", "h3", "li"]):
        text = _clean(el.get_text(" "))
        if not text:
            continue
        if text == "###":
            current = current or "_after"
            continue
        if el.name in ("h3", "h4"):
            current = text.lower()
            sections.setdefault(current, [])
            continue
        if current is None:
            intro.append(text)
        else:
            sections.setdefault(current, []).append(text)

    # 介绍的最后一段若是 "A. B. C." 形式的短规格（每句都很短）→ Feature，否则仍算描述
    feature_parts: List[str] = []
    if len(intro) > 1:
        parts = [s.strip() for s in intro[-1].split(".") if s.strip()]
        if parts and all(len(p.split()) <= 8 for p in parts):
            feature_parts = parts
            intro = intro[:-1]
    description = " ".join(intro)

    fit = " ".join(sections.get("size & fit", []))
    fit_first = fit.split(".")[0].strip() if fit else ""
    if fit_first and fit_first not in feature_parts:
        feature_parts.append(fit_first)
    if not feature_parts and description:
        feature_parts = [description.split(".")[0].strip()]
    feature = " | ".join(feature_parts)

    details = " ".join(sections.get("details", []))
    comp = re.findall(r"[^.]*\d+\s*%[^.]*", details)
    material = "; ".join(_clean(c) for c in comp)

    return description, feature, material


# ================= 尺码 =================
def parse_sizes(product: dict) -> Tuple[Dict[str, str], Dict[str, dict]]:
    size_idx = 1
    for i, opt in enumerate(product.get("options") or []):
        name = opt.get("name") if isinstance(opt, dict) else str(opt)
        if (name or "").lower() == "size":
            size_idx = i

    size_map: Dict[str, str] = {}
    size_detail: Dict[str, dict] = {}
    for v in product.get("variants") or []:
        opts = v.get("options") or [v.get("option1"), v.get("option2"), v.get("option3")]
        size = _clean(str(opts[size_idx] if len(opts) > size_idx and opts[size_idx] else v.get("title") or ""))
        if not size:
            continue
        in_stock = bool(v.get("available"))
        # 同尺码多条 variant 时，任一有货即有货
        if size_map.get(size) == "有货":
            continue
        size_map[size] = "有货" if in_stock else "无货"
        size_detail[size] = {
            "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
            "ean": (v.get("barcode") or "").strip() or "0000000000000",
        }
    return size_map, size_detail


def _gender(product: dict, url: str, meta: Dict[str, dict]) -> str:
    g = tag_value(product.get("tags") or [], "gender")
    if g.lower() in ("women", "men"):
        return g.capitalize()
    genders = (meta.get(url) or {}).get("genders") or []
    if len(genders) == 1:
        return genders[0]
    return g or "Unisex"


def _style_category(product_type: str) -> str:
    return re.sub(r"^(Women's|Men's|Womens|Mens)\s+", "", product_type or "", flags=re.I).strip()


def parse_toast_product(product: dict, url: str, meta: Dict[str, dict]) -> dict:
    title = product.get("title") or ""
    name = _clean(title.split("|")[0]) or title

    colour = ""
    variants = product.get("variants") or []
    if variants:
        colour = _clean(variants[0].get("option1") or "")
    if not colour and "|" in title:
        colour = _clean(title.split("|", 1)[1])

    price = _pence_to_gbp(product.get("price"))
    compare = _pence_to_gbp(product.get("compare_at_price"))
    original = compare if compare > price else price

    description, feature, material = parse_description(product.get("description") or "")
    if not material:
        material = tag_value(product.get("tags") or [], "material")
    size_map, size_detail = parse_sizes(product)

    return {
        "Product Code": derive_product_code(product),
        "Product Name": name or "No Name",
        "Product Description": description or "No Data",
        "Product Gender": _gender(product, url, meta),
        "Product Color": colour,
        "Product Price": str(original),
        "Adjusted Price": str(price or original),
        "Product Material": material or "No Data",
        "Style Category": _style_category(product.get("type") or ""),
        "Feature": feature or "No Data",
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Site Name": product.get("vendor") or "TOAST",
        "Source URL": url,
    }


def fetch_one_and_write(url: str, save_dir: Path, meta: Dict[str, dict]) -> Tuple[str, bool, str]:
    try:
        product = fetch_product_js(url)
        info = parse_toast_product(product, url, meta)
        path = Path(save_dir) / f"{info['Product Code']}.txt"
        format_txt(info, path, brand="toast")
        return url, True, ""
    except Exception as e:
        print(f"💥 解析失败：{url} -> {e}")
        return url, False, f"{handle_from_url(url)}: {e}"


def toast_fetch_all(
    urls_file: Optional[Path] = None,
    save_dir: Optional[Path] = None,
    max_workers: int = 6,
) -> None:
    urls_file = Path(urls_file or TOAST["LINKS_FILE"])
    save_dir = Path(save_dir or TOAST["TXT_DIR"])
    save_dir.mkdir(parents=True, exist_ok=True)

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = list(dict.fromkeys(u.strip() for u in f if u.strip()))
    meta = _load_meta(urls_file)

    print(f"📦 共 {len(urls)} 个链接，开始抓取 → {save_dir}")
    ok, errs = 0, []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(fetch_one_and_write, u, save_dir, meta) for u in urls]
        for fut in as_completed(futs):
            _, success, msg = fut.result()
            if success:
                ok += 1
            else:
                errs.append(msg)

    print(f"🎯 完成：成功 {ok}，失败 {len(errs)}，输出目录：{save_dir}")
    if errs:
        print("⚠️ 失败示例：", errs[:5])


if __name__ == "__main__":
    toast_fetch_all()
