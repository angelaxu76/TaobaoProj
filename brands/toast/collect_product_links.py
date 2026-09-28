# -*- coding: utf-8 -*-
"""
TOAST 商品链接抓取（Shopify products.json，无需浏览器）

- 类目来自 TOAST["COLLECTIONS"]（男女款衣服 + 配件）
- 按 VENDOR_FILTER / EXCLUDE_PRODUCT_TYPE_KEYWORDS 过滤
- 输出：
    LINKS_FILE                     全部商品链接（去重、排序）
    links_{collection}.txt         每个类目的链接
    links_meta.json                url -> 所属类目/性别，fetch 时用于补性别
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from config import TOAST
from brands.toast.shopify_api import iter_collection_products, product_url

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")


def _keep(product: dict, vendors: Optional[List[str]], exclude_type_kw: List[str]) -> bool:
    if vendors and (product.get("vendor") or "") not in vendors:
        return False
    ptype = (product.get("product_type") or "").lower()
    return not any(kw.lower() in ptype for kw in exclude_type_kw)


def toast_get_links(
    collections: Optional[Dict[str, str]] = None,
    output_file: Optional[Path] = None,
) -> Path:
    collections = collections or TOAST["COLLECTIONS"]
    out_path = Path(output_file) if output_file else Path(TOAST["LINKS_FILE"])
    vendors = TOAST.get("VENDOR_FILTER")
    exclude_type_kw = TOAST.get("EXCLUDE_PRODUCT_TYPE_KEYWORDS") or []

    meta: Dict[str, dict] = {}

    for idx, (coll, gender) in enumerate(collections.items(), 1):
        print(f"\n▶ 类目 [{idx}/{len(collections)}]: {coll} ({gender})")
        try:
            products = iter_collection_products(coll)
        except Exception as e:
            print(f"💥 类目抓取失败，跳过：{e}")
            continue

        cat_links: List[str] = []
        skipped = 0
        for p in products:
            if not _keep(p, vendors, exclude_type_kw):
                skipped += 1
                continue
            url = product_url(p["handle"])
            cat_links.append(url)
            m = meta.setdefault(url, {"collections": [], "genders": []})
            if coll not in m["collections"]:
                m["collections"].append(coll)
            if gender and gender not in m["genders"]:
                m["genders"].append(gender)

        _write_lines(out_path.with_name(f"links_{coll}.txt"), sorted(set(cat_links)))
        print(f"   ✅ 共 {len(products)} 个商品，保留 {len(cat_links)}，过滤 {skipped}")

    all_links = sorted(meta.keys())
    _write_lines(out_path, all_links)
    with open(out_path.with_name("links_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print(f"\n📝 已保存 {len(all_links)} 条链接 → {out_path}")
    return out_path


if __name__ == "__main__":
    toast_get_links()
