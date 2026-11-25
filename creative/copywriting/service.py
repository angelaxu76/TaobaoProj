# -*- coding: utf-8 -*-
"""按品牌批量生成文案（不入库，返回 (商品, 文案) 列表）。"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from cfg.creative_config import COPY_LABELS
from creative.copywriting.naming import build_names, extract_series, infer_category, series_core
from creative.copywriting.safe_copy import generate_safe
from creative.copywriting.selling_points import FIELDS as POINT_FIELDS, generate_selling_points
from creative.copywriting.series_names import resolve_series_cn
from creative.product_source import ProductInfo, load_products


def build_copy(p: ProductInfo, series_map: dict[str, str], use_ai: bool = True, old: dict | None = None,
               mode: str = "safe") -> dict:
    """生成单个商品的全部文案。old 中已有的非空字段原样保留，只补缺的。
    mode: safe = 只用可核实事实 + 中性短语（默认，不调用 AI）；ai = DeepSeek 撰写 + 校验。"""
    old = {k: v for k, v in (old or {}).items() if v}
    series = extract_series(p)
    cat = infer_category(p, series)
    cn = series_map.get(series_core(series), "")
    if all(old.get(f) for f in POINT_FIELDS):
        points = {"copy_source": "reuse"}
    elif mode == "safe":
        points = generate_safe(p, cat)
    else:
        points = generate_selling_points(p, cat, use_ai)
    return {**build_names(p, series, cn, cat), **points, **old,
            "series_en": series, "series_cn": cn, "category_cn": cat}


def generate_for_brand(brand: str, source: str = "db", scope: str = "published", codes: list[str] | None = None,
                       use_ai: bool = True, limit: int | None = None, workers: int = 8,
                       reuse: dict[tuple[str, str], dict] | None = None, mode: str = "safe"
                       ) -> list[tuple[ProductInfo, dict]]:
    """reuse: {(品牌, 商品编码): 已有文案}，来自之前的 Excel（copy_excel.read_copy_excel）。mode 见 build_copy。"""
    if mode not in ("safe", "ai"):
        raise ValueError(f"❌ mode 只能是 safe / ai：{mode}")
    brand = brand.lower().strip()
    reuse = reuse or {}
    products = load_products(brand, source, scope, codes)
    no_detail = [p.product_code for p in products if not p.has_detail]
    products = [p for p in products if p.has_detail][:limit]
    print(f"📦 [{brand}] 待处理 {len(products)} 个商品")

    results: dict[str, dict] = {}
    if products:
        series_map = resolve_series_cn(brand, {series_core(extract_series(p)) for p in products}, use_ai)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(build_copy, p, series_map, use_ai, reuse.get((brand, p.product_code)), mode): p
                       for p in products}
            for i, fut in enumerate(as_completed(futures), 1):
                code = futures[fut].product_code
                try:
                    results[code] = fut.result()
                except Exception as e:
                    print(f"❌ [{brand}] {code} 生成失败：{e}")
                if i % 50 == 0:
                    print(f"   … {i}/{len(products)}")

    if no_detail:
        print(f"⚠️ [{brand}] {len(no_detail)} 个商品没有英文标题，已跳过：{', '.join(no_detail[:10])}"
              f"{' …' if len(no_detail) > 10 else ''}")
    incomplete = [c for c, r in results.items() if not all(r.get(f) for f in COPY_LABELS)]
    if incomplete:
        print(f"⚠️ [{brand}] {len(incomplete)} 个商品有空字段，需人工补：{', '.join(incomplete[:10])}")
    print(f"✅ [{brand}] 完成 {len(results)} 个，卖点来源 {dict(Counter(r['copy_source'] for r in results.values()))}")
    return [(p, results[p.product_code]) for p in products if p.product_code in results]
