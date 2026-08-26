# -*- coding: utf-8 -*-
"""
tool_inspect_supplier.py
========================
诊断工具：输入一个商品编码，输出：
  1. 所有供货商在该商品上的逐尺码库存 + 价格明细
  2. 各供货商的汇总（有货尺码数、有效成本价）
  3. allocate_and_sync 会自动选出的供应商组合（贪心算法预览，不写库）
  4. 当前 barbour_supplier_allocation 里已落库的分配（若已跑过 allocate_and_sync）

用法：
  python -m brands.barbour.pipeline.tool_inspect_supplier LBE0042NY11
  python -m brands.barbour.pipeline.tool_inspect_supplier          # 交互式输入
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd
from sqlalchemy import text

from brands.barbour.jingya.allocate_supplier_and_price import (
    _get_engine,
    select_suppliers_for_code,
)
from brands.barbour.jingya.allocate_supplier_and_price_config import (
    SUPPLIER_MIN_SIZES,
    SUPPLIER_MAX_SITES,
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
  size,
  COALESCE(stock_count, 0)          AS stock_count,
  original_price_gbp,
  sale_price_gbp,
  price_gbp,
  last_checked
FROM barbour_offers
WHERE product_code = :code
  AND is_active = TRUE
ORDER BY site_name, size
""")

_SQL_CURRENT_ALLOC = text("""
SELECT site_name, rank, min_eff_price, sizes_in_stock, is_price_basis, source, updated_at
FROM barbour_supplier_allocation
WHERE product_code = :code
ORDER BY rank
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
        alloc_rows = conn.execute(_SQL_CURRENT_ALLOC, {"code": code}).fetchall()
        pub_row = conn.execute(_SQL_IS_PUBLISHED, {"code": code}).fetchone()

    if not rows:
        print(f"\n[!] 数据库中找不到商品 {code!r} 的任何 active offer，请确认编码是否正确。")
        return

    is_published: Optional[bool] = pub_row[0] if pub_row else None
    current_sites = [r[0] for r in alloc_rows]

    _sep("═")
    print(f"  商品编码：{code}")
    print(f"  已发布状态：{'是' if is_published else '否' if is_published is False else '(inventory 中无记录)'}")
    if alloc_rows:
        print("  当前 barbour_supplier_allocation 分配：")
        for site, rank, price, sizes, is_basis, source, updated in alloc_rows:
            tag = "  ← 定价依据" if is_basis else ""
            print(f"    #{rank} {site}  成本£{price:.2f}  有货{sizes}尺  来源={source}{tag}")
    else:
        print("  当前 barbour_supplier_allocation 分配：(无，尚未跑过 allocate_and_sync)")
    _sep("═")

    # ── 构造 DataFrame ───────────────────────
    df = pd.DataFrame(rows, columns=[
        "site_name", "size", "stock_count",
        "original_price_gbp", "sale_price_gbp", "price_gbp", "last_checked",
    ])
    df["site_name"] = df["site_name"].map(lambda s: canonical_site(s) or s)
    df["stock_count"] = df["stock_count"].fillna(0).astype(int)

    # 有效成本价（sale_price_gbp 已含折扣策略+运费，优先；否则 price_gbp，再否则 original_price_gbp）
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
        marker = "  ◀ 当前已选" if site in current_sites else ""
        print(f"  ┌── {site}{marker}")
        sub = df[df["site_name"] == site].sort_values("size")
        for _, r in sub.iterrows():
            stock_tag = f"{'有货':>3}({r['stock_count']:>2})" if r["stock_count"] > 0 else "  无货   "
            print(
                f"  │  {str(r['size'] or '').ljust(12)}"
                f"  {stock_tag}"
                f"  原价:{_fmt_price(r['original_price_gbp'])}"
                f"  折后:{_fmt_price(r['sale_price_gbp'])}"
                f"  有效成本:{_fmt_price(r['eff_price'])}"
            )
        _sep("─", 60)

    # ════════════════════════════════════════
    #  第 2 节：按供货商汇总
    # ════════════════════════════════════════
    print("\n[2] 供货商汇总（有货尺码数 / 最低有效成本）\n")

    summary_rows = []
    for site in all_sites:
        sub = df[df["site_name"] == site]
        in_stock = sub[sub["stock_count"] > 0]
        sizes_in_stock = len(in_stock)
        min_eff = in_stock["eff_price"].min() if not in_stock.empty else None
        latest = sub["last_checked"].max()
        summary_rows.append({
            "供货商": site,
            "有货尺码数": sizes_in_stock,
            "有效成本(£)": round(float(min_eff), 2) if min_eff and min_eff == min_eff else None,
            "最近更新": str(latest)[:19] if latest is not None else "-",
            "当前已选": "✓" if site in current_sites else "",
        })

    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))

    # ════════════════════════════════════════
    #  第 3 节：allocate_and_sync 会选出的组合（预览，不写库）
    # ════════════════════════════════════════
    min_sizes = SUPPLIER_MIN_SIZES
    max_sites = SUPPLIER_MAX_SITES
    print(f"\n[3] 自动分配预览（min_sizes={min_sizes}, max_suppliers={max_sites}）\n")

    preview = select_suppliers_for_code(code, min_sizes=min_sizes, max_suppliers=max_sites)
    if not preview["chosen"]:
        print("  (无合适候选：没有供应商同时满足有货+有效价)")
    else:
        for c in preview["chosen"]:
            is_basis = c["min_eff_price"] == preview["price_basis"]
            tag = "  ← 定价依据（最贵者）" if is_basis else ""
            print(f"  {c['site']:<20} 成本£{c['min_eff_price']:.2f}  有货{c['sizes_in_stock']}尺{tag}")
        print(f"\n  覆盖尺码数：{len(preview['covered_sizes'])}  |  定价基准：£{preview['price_basis']:.2f}")

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
