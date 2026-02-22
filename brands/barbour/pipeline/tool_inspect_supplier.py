# -*- coding: utf-8 -*-
"""
tool_inspect_supplier.py
========================
诊断工具：输入一个商品编码，输出：
  1. 所有供货商在该商品上的逐尺码库存 + 价格明细
  2. 各供货商的汇总（有货尺码数、最低网页价、真实落地成本）
  3. 各策略选出的最优供货商
  4. 当前 barbour_supplier_map 的已有映射

用法：
  python -m brands.barbour.pipeline.tool_inspect_supplier LBE0042NY11
  python -m brands.barbour.pipeline.tool_inspect_supplier          # 交互式输入
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd
from sqlalchemy import text

from brands.barbour.common.build_supplier_jingya_mapping_v2 import (
    BandStockStrategy,
    LowestPriceStrategy,
    MostStockStrategy,
    PreferredSiteStrategy,
    TrueCostStrategy,
    _get_engine,
    _true_cost,
)
from brands.barbour.core.site_utils import canonical_site

pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 160)
pd.set_option("display.float_format", "{:.2f}".format)

# ──────────────────────────────────────────────
#  SQL
# ──────────────────────────────────────────────
_SQL_OFFERS = text("""
SELECT
  site_name,
  size_norm,
  COALESCE(stock_count, 0)          AS stock_count,
  original_price_gbp,
  sale_price_gbp,
  price_gbp,
  last_checked
FROM barbour_offers
WHERE product_code = :code
  AND is_active = TRUE
ORDER BY site_name, size_norm
""")

_SQL_CURRENT_MAP = text("""
SELECT site_name
FROM barbour_supplier_map
WHERE product_code = :code
""")

_SQL_IS_PUBLISHED = text("""
SELECT is_published
FROM barbour_inventory
WHERE product_code = :code
LIMIT 1
""")


# ──────────────────────────────────────────────
#  格式化辅助
# ──────────────────────────────────────────────
def _sep(char: str = "─", width: int = 72) -> None:
    print(char * width)


def _fmt_price(v) -> str:
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return "    -  "
    return f"£{float(v):>7.2f}"


# ──────────────────────────────────────────────
#  核心逻辑
# ──────────────────────────────────────────────
def inspect(product_code: str) -> None:
    code = product_code.strip().upper()
    engine = _get_engine()

    with engine.connect() as conn:
        rows = conn.execute(_SQL_OFFERS, {"code": code}).fetchall()
        cur_map_row = conn.execute(_SQL_CURRENT_MAP, {"code": code}).fetchone()
        pub_row = conn.execute(_SQL_IS_PUBLISHED, {"code": code}).fetchone()

    if not rows:
        print(f"\n[!] 数据库中找不到商品 {code!r} 的任何 active offer，请确认编码是否正确。")
        return

    # ── 基础信息 ─────────────────────────────
    current_site: Optional[str] = (
        canonical_site(cur_map_row[0]) or cur_map_row[0] if cur_map_row else None
    )
    is_published: Optional[bool] = pub_row[0] if pub_row else None

    _sep("═")
    print(f"  商品编码：{code}")
    print(f"  已发布状态：{'是' if is_published else '否' if is_published is False else '(inventory 中无记录)'}")
    print(f"  当前 supplier_map 映射：{current_site or '(无)'}")
    _sep("═")

    # ── 构造 DataFrame ───────────────────────
    df = pd.DataFrame(rows, columns=[
        "site_name", "size_norm", "stock_count",
        "original_price_gbp", "sale_price_gbp", "price_gbp", "last_checked",
    ])
    df["site_name"] = df["site_name"].map(lambda s: canonical_site(s) or s)
    df["stock_count"] = df["stock_count"].fillna(0).astype(int)

    # 计算真实落地成本（逐行）
    df["true_cost"] = df.apply(
        lambda r: _true_cost(r["site_name"], r["original_price_gbp"], r["sale_price_gbp"]),
        axis=1,
    )
    # 有效网页价（sale 优先，其次 price_gbp，再次 original）
    df["eff_price"] = df.apply(
        lambda r: (
            r["sale_price_gbp"] if (r["sale_price_gbp"] or 0) > 0
            else r["price_gbp"] if (r["price_gbp"] or 0) > 0
            else r["original_price_gbp"]
        ),
        axis=1,
    )

    all_sites = sorted(df["site_name"].unique())

    # ════════════════════════════════════════
    #  第 1 节：逐供货商 × 逐尺码明细
    # ════════════════════════════════════════
    print("\n[1] 逐供货商 · 尺码库存 & 价格明细\n")
    for site in all_sites:
        marker = "  ◀ 当前映射" if site == current_site else ""
        print(f"  ┌── {site}{marker}")
        sub = df[df["site_name"] == site].sort_values("size_norm")
        for _, r in sub.iterrows():
            stock_tag = f"{'有货':>3}({r['stock_count']:>2})" if r["stock_count"] > 0 else "  无货   "
            print(
                f"  │  {str(r['size_norm'] or '').ljust(12)}"
                f"  {stock_tag}"
                f"  原价:{_fmt_price(r['original_price_gbp'])}"
                f"  折后:{_fmt_price(r['sale_price_gbp'])}"
                f"  网页有效:{_fmt_price(r['eff_price'])}"
                f"  落地成本:{_fmt_price(r['true_cost']) if r['true_cost'] > 0 else '    -  '}"
            )
        _sep("─", 60)

    # ════════════════════════════════════════
    #  第 2 节：按供货商汇总
    # ════════════════════════════════════════
    print("\n[2] 供货商汇总（有货尺码数 / 最低网页价 / 最低落地成本）\n")

    summary_rows = []
    for site in all_sites:
        sub = df[df["site_name"] == site]
        in_stock = sub[sub["stock_count"] > 0]
        sizes_in_stock = len(in_stock)
        min_eff = in_stock["eff_price"].min() if not in_stock.empty else None
        min_cost = in_stock["true_cost"].min() if not in_stock.empty else None
        latest = sub["last_checked"].max()
        summary_rows.append({
            "供货商": site,
            "有货尺码数": sizes_in_stock,
            "最低网页价(£)": round(float(min_eff), 2) if min_eff and min_eff == min_eff else None,
            "最低落地成本(£)": round(float(min_cost), 2) if min_cost and min_cost == min_cost else None,
            "最近更新": str(latest)[:19] if latest is not None else "-",
            "当前映射": "✓" if site == current_site else "",
        })

    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))

    # ════════════════════════════════════════
    #  第 3 节：各策略的选择结果
    # ════════════════════════════════════════
    print("\n[3] 各策略选择结果（min_sizes=3）\n")

    strategies = [
        ("LowestPriceStrategy (默认)", LowestPriceStrategy(min_sizes=3)),
        ("MostStockStrategy",          MostStockStrategy(min_sizes=3)),
        ("TrueCostStrategy",           TrueCostStrategy(min_sizes=3)),
        ("BandStockStrategy (band=20%)", BandStockStrategy(min_sizes=3, band_ratio=0.20)),
    ]

    with engine.connect() as conn:
        for label, strat in strategies:
            try:
                selected = strat.select(conn, code)
            except Exception as e:
                selected = f"(出错: {e})"
            marker = "  ◀ 与当前映射一致" if selected == current_site else ""
            print(f"  {label:<38}  ->  {selected or '(无合适候选)'}{marker}")

    # ── 补充：min_sizes=1 的宽松版本（供参考）
    print()
    print("  --- 宽松版（min_sizes=1，有至少1个尺码有货即可） ---")
    with engine.connect() as conn:
        for label, strat_cls, kwargs in [
            ("LowestPriceStrategy", LowestPriceStrategy, {"min_sizes": 1}),
            ("TrueCostStrategy",    TrueCostStrategy,    {"min_sizes": 1}),
        ]:
            try:
                selected = strat_cls(**kwargs).select(conn, code)
            except Exception as e:
                selected = f"(出错: {e})"
            print(f"  {label:<38}  ->  {selected or '(无合适候选)'}")

    _sep("═")
    print("  完成。\n")


# ──────────────────────────────────────────────
#  入口
# ──────────────────────────────────────────────
def main() -> None:
    if len(sys.argv) >= 2:
        code = sys.argv[1]
    else:
        code = input("请输入商品编码（product_code）：").strip()

    if not code:
        print("未输入编码，退出。")
        sys.exit(1)

    inspect(code)


if __name__ == "__main__":
    main()
