# -*- coding: utf-8 -*-
"""
Barbour 供应商 / 价格 / 库存 —— 单一入口

替代原本分散在 build_supplier_jingya_mapping.py（v1/v2）、
merge_offer_into_inventory.py、db_build_supplier_map_and_inventory.py
里的"选供应商 → 算价格 → 算库存"逻辑。

核心策略（allocate_and_sync）：由 session_config.SUPPLIER_STRATEGY 选择——
"fill_sizes"（策略二）见 _select_sites_by_fill_sizes；下面描述的是
"price_window"（策略一）：
- 每个已发布商品，按"真实落地成本"（barbour_offers.sale_price_gbp——
  已在导入阶段套用过 SUPPLIER_DISCOUNT_RULES 的折扣比例 + 运费，见
  import_supplier_to_db_offers.compute_supplier_sale_price；取不到则
  COALESCE 到 price_gbp / original_price_gbp 兜底）找出成本最低的供应商
  作为基准，凡是成本不超过"基准 × (1 + SUPPLIER_PRICE_TOLERANCE_PCT)"
  的供应商都一并纳入（最多凑满 SUPPLIER_MAX_SITES 家）——即使窗口内供
  应商合计的有货尺码数不多，也不会为了凑尺码去找窗口外更贵的供应商。
- 最终库存 = 所选各站点"有货尺码"的并集。
- 最终定价 = 所选各站点里成本最高的那个（避免低价站点断货、临时改用
  高价站点补货时倒贴运费亏本）。

人工干预（两个独立 Excel，都按鲸芽"渠道商品ID"整组生效，可叠加）：
- 手动库存 MANUAL_STOCK_XLSX（load_manual_stock）：列 渠道商品ID / 供货商
  · 只填 ID     → 照常自动分配，但阶段 D 导出鲸芽库存时跳过（鲸芽端手动维护）
  · ID + 供货商 → 该 ID 下所有颜色只用这个供货商的库存，正常导出
- 手动价格 MANUAL_PRICE_XLSX（load_manual_price）：列 渠道商品ID /
  source_price_gbp / discount_price_gbp
  · 填了价格    → 自动分配后由 _apply_fixed_prices() 覆盖为人工价
  · 价格留空    → 不做同款价格对齐，阶段 D 不导出鲸芽/淘宝价格（沿用平台价）
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import openpyxl
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import BRAND_CONFIG, BARBOUR, DEFAULT_STOCK_COUNT
from brands.barbour.core.site_utils import canonical_site
from common.product.size_utils import clean_size_for_barbour
from common.pricing.price_utils import calculate_jingya_prices
from brands.barbour.jingya.allocate_supplier_and_price_config import (
    SUPPLIER_STRATEGY,
    FILL_SIZES_TARGET,
    FILL_SIZES_MAX_SITES,
    SUPPLIER_PRICE_TOLERANCE_PCT,
    SUPPLIER_MAX_SITES,
    SUPPLIER_MIN_SIZES_IN_STOCK,
    TAOBAO_STORE_DISCOUNT,
    MANUAL_STOCK_XLSX,
    MANUAL_PRICE_XLSX,
)

TABLE_ALLOC = "barbour_supplier_allocation"
PUBLICATION_DIR = Path(BARBOUR["PUBLICATION_DIR"])
PUB_PATTERN = "barbour_publication_*.xlsx"

SQL_CREATE_ALLOC = text(f"""
CREATE TABLE IF NOT EXISTS {TABLE_ALLOC} (
  product_code   VARCHAR(50)  NOT NULL,
  site_name      VARCHAR(100) NOT NULL,
  rank           SMALLINT     NOT NULL,
  min_eff_price  NUMERIC(10,2),
  sizes_in_stock INT,
  is_price_basis BOOLEAN DEFAULT FALSE,
  source         VARCHAR(20) DEFAULT 'auto',
  updated_at     TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (product_code, site_name)
);
""")


# ═══════════════════════════════════════════════════════════════════
#  基础工具
# ═══════════════════════════════════════════════════════════════════

def _get_engine() -> Engine:
    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    return create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )


def _ensure_price_columns(conn) -> None:
    conn.execute(text("""
        ALTER TABLE barbour_inventory
          ADD COLUMN IF NOT EXISTS jingya_untaxed_price NUMERIC(12,2),
          ADD COLUMN IF NOT EXISTS taobao_store_price   NUMERIC(12,2),
          ADD COLUMN IF NOT EXISTS base_price_gbp       NUMERIC(10,2),
          ADD COLUMN IF NOT EXISTS exchange_rate_used   NUMERIC(8,4)
    """))


def _normalize_channel_id(v) -> str:
    """鲸芽渠道商品ID 统一成纯数字字符串（兼容 Excel 里存成数字/科学计数法/带 .0 的情况）。"""
    s = str(v if v is not None else "").strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    if "e" in s.lower():
        try:
            s = str(int(Decimal(s)))
        except InvalidOperation:
            pass
    if s.endswith(".0"):
        s = s[:-2]
    return s


_ID_COL_KEYS = ("渠道商品id", "渠道产品id", "channel_product_id", "商品id")
_SITE_COL_KEYS = ("供货商", "供应商", "supplier", "site")


def _read_channel_id_sheet(xlsx_path: Optional[str], label: str) -> Optional[pd.DataFrame]:
    """
    读手动清单 Excel（第一个 sheet），返回带规范化 "cid" 列的 DataFrame；
    文件不存在 / 没有渠道商品ID列时返回 None。
    """
    if not xlsx_path:
        return None
    if not Path(xlsx_path).exists():
        print(f"ℹ️ {label}文件不存在，已跳过：{xlsx_path}")
        return None
    df = pd.read_excel(xlsx_path, dtype=str)
    col_map = {str(c).strip().lower().replace(" ", ""): c for c in df.columns}
    id_col = next((col_map[k] for k in _ID_COL_KEYS if k in col_map), None)
    if not id_col:
        print(f"⚠️ {label}中没有「渠道商品ID」列，已忽略：{list(df.columns)}")
        return None
    df["cid"] = df[id_col].map(_normalize_channel_id)
    df = df[df["cid"] != ""]
    df.attrs["col_map"] = col_map
    return df


def load_manual_stock(xlsx_path: Optional[str]) -> Tuple[Set[str], Dict[str, str]]:
    """
    读手动库存清单（列：渠道商品ID / 供货商），返回 (skip_ids, forced_site_by_id)：
    - 只填 ID              → skip_ids：阶段 D 导出鲸芽库存时整组跳过
    - ID + 可识别的供货商  → forced_site_by_id：该 ID 下所有颜色只用这个供货商
    供货商填了但识别不出来的行，按"跳过导出"处理并打印警告——宁可不推库存，
    也不推一个来源不明的库存到鲸芽。
    """
    df = _read_channel_id_sheet(xlsx_path, "手动库存清单")
    if df is None:
        return set(), {}
    col_map = df.attrs["col_map"]
    site_col = next((col_map[k] for k in _SITE_COL_KEYS if k in col_map), None)

    skip_ids: Set[str] = set()
    forced: Dict[str, str] = {}
    for _, row in df.iterrows():
        cid = row["cid"]
        site_raw = str(row.get(site_col) or "").strip() if site_col else ""
        if site_raw.lower() == "nan":
            site_raw = ""
        if not site_raw:
            skip_ids.add(cid)
            continue
        site = canonical_site(site_raw)
        if site:
            forced[cid] = site
        else:
            print(f"⚠️ 手动库存清单：渠道商品ID {cid} 的供货商「{site_raw}」无法识别，按跳过库存导出处理。")
            skip_ids.add(cid)
    return skip_ids, forced


def load_manual_price(xlsx_path: Optional[str]) -> Tuple[Set[str], Dict[str, Tuple[Optional[float], Optional[float]]]]:
    """
    读手动价格清单（列：渠道商品ID / source_price_gbp / discount_price_gbp），
    返回 (locked_ids, fixed_price_by_id)：
    - 两个价格都留空 → locked_ids：阶段 D 不导出鲸芽/淘宝价格，也不参与同款价格对齐
    - 填了价格       → fixed_price_by_id[cid] = (source_price_gbp, discount_price_gbp)
    """
    df = _read_channel_id_sheet(xlsx_path, "手动价格清单")
    if df is None:
        return set(), {}
    col_map = df.attrs["col_map"]

    def _num(row, key):
        col = col_map.get(key)
        if not col:
            return None
        v = pd.to_numeric(row.get(col), errors="coerce")
        return None if pd.isna(v) or float(v) <= 0 else float(v)

    locked: Set[str] = set()
    fixed: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for _, row in df.iterrows():
        src, disc = _num(row, "source_price_gbp"), _num(row, "discount_price_gbp")
        if src is None and disc is None:
            locked.add(row["cid"])
        else:
            fixed[row["cid"]] = (src, disc)
    return locked, fixed


def codes_by_channel_id(ids, engine: Optional[Engine] = None) -> Dict[str, Set[str]]:
    """按 barbour_inventory 把渠道商品ID 展开成其下全部颜色编码；库中找不到的 ID 打印警告。"""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    engine = engine or _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT TRIM(channel_product_id) AS cid, product_code
            FROM barbour_inventory
            WHERE TRIM(channel_product_id) = ANY(:ids)
              AND product_code IS NOT NULL AND product_code <> ''
        """), {"ids": list(ids)}).fetchall()
    out: Dict[str, Set[str]] = {}
    for cid, code in rows:
        out.setdefault(_normalize_channel_id(cid), set()).add(code)
    missing = sorted(ids - set(out))
    if missing:
        print(f"⚠️ 以下渠道商品ID在 barbour_inventory 中找不到（未发布或填错）：{', '.join(missing)}")
    return out


def _expand(ids, by_id: Dict[str, Set[str]]) -> Set[str]:
    codes: Set[str] = set()
    for cid in ids:
        codes |= by_id.get(cid, set())
    return codes


def _load_publication_mappings(pub_dir: Path) -> Dict[str, str]:
    """
    新品刚在鲸芽发布、还没抓到任何供应商 offer 时的兜底：
    读历史 barbour_publication_*.xlsx 里记录的供应商（后读的新文件覆盖旧文件）。
    """
    def _headers(ws) -> Dict[str, int]:
        h = {}
        for j, c in enumerate(ws[1], start=1):
            k = str(c.value or "").strip().lower().replace(" ", "")
            if k:
                h[k] = j
        return h

    mappings: Dict[str, str] = {}
    if not pub_dir.exists():
        return mappings
    files = sorted(pub_dir.glob(PUB_PATTERN), key=lambda p: p.stat().st_mtime)
    for fp in files:
        try:
            wb = openpyxl.load_workbook(fp, data_only=True)
            ws = wb.active
            hdr = _headers(ws)
            col_code = next((hdr[k] for k in ("productcode", "商品编码", "product_code", "color_code", "编码") if k in hdr), None)
            col_site = next((hdr[k] for k in ("supplier", "供应商", "site", "站点") if k in hdr), None)
            if not col_code or not col_site:
                continue
            for i in range(2, ws.max_row + 1):
                code = str(ws.cell(i, col_code).value or "").strip()
                site_raw = str(ws.cell(i, col_site).value or "").strip()
                if not code or not site_raw:
                    continue
                site = canonical_site(site_raw)
                if site:
                    mappings[code] = site
        except Exception as e:
            print(f"⚠️ 解析发布清单失败 {fp.name}: {e}")
    return mappings


def _reconcile_shared_channel_prices(engine: Engine, dry_run: bool, locked_ids: Optional[Set[str]] = None) -> int:
    """
    同一个鲸芽 channel_product_id 下可能对应多个 product_code（比如同一款式
    的两个颜色，各自是独立编码，但共用一个鲸芽商品listing）。allocate_and_sync
    是按 product_code 独立算价的，两个颜色可能分到不同供应商、算出不同价格；
    但鲸芽一个 channel_product_id 只能设一个"通用渠道价格"，下游导出脚本
    （export_channel_price_excel_jingya.py，多品牌共用，这里不动它）按
    channel_product_id 分组时是 .agg("first")，会随手挑其中一个颜色的价格
    上传，另一个颜色算出来的价格就被丢弃、可能让那个颜色实际卖亏。

    所以在这里、写库层面统一：同一 channel_product_id 下，找出定价基准
    （base_price_gbp）最高的那个颜色，把它的价格字段整组同步给同 listing
    下的其它颜色，这样不管下游导出脚本挑到哪一行，价格都是一致的、且是
    组内最高（最不容易亏本）的那个。

    只对接标的价格字段做同步（不动库存），返回受影响的 product_code 数。
    locked_ids（手动价格清单里的 ID）整组跳过——价格由人工决定。
    """
    with engine.connect() as conn:
        grp = pd.read_sql(text("""
            SELECT DISTINCT product_code, channel_product_id, base_price_gbp,
                   jingya_untaxed_price, taobao_store_price,
                   source_price_gbp, original_price_gbp, discount_price_gbp
            FROM barbour_inventory
            WHERE channel_product_id IS NOT NULL AND TRIM(channel_product_id) <> ''
              AND base_price_gbp IS NOT NULL
        """), conn)

    if grp.empty:
        return 0

    updates: List[dict] = []
    locked_ids = locked_ids or set()
    for channel_id, g in grp.groupby("channel_product_id"):
        if _normalize_channel_id(channel_id) in locked_ids:
            continue  # 人工锁价的 listing，不参与对齐
        if g["product_code"].nunique() <= 1:
            continue  # 这个 listing 只有一个 product_code，没有分叉风险
        if g["base_price_gbp"].nunique() <= 1:
            continue  # 组内价格已经一致，不需要处理

        winner = g.loc[g["base_price_gbp"].idxmax()]
        for _, row in g.iterrows():
            if row["product_code"] == winner["product_code"]:
                continue
            if row["base_price_gbp"] == winner["base_price_gbp"]:
                continue
            updates.append({
                "product_code": row["product_code"],
                "base_price_gbp": float(winner["base_price_gbp"]),
                "jingya_untaxed_price": None if pd.isna(winner["jingya_untaxed_price"]) else float(winner["jingya_untaxed_price"]),
                "taobao_store_price": None if pd.isna(winner["taobao_store_price"]) else float(winner["taobao_store_price"]),
                "source_price_gbp": None if pd.isna(winner["source_price_gbp"]) else float(winner["source_price_gbp"]),
                "original_price_gbp": None if pd.isna(winner["original_price_gbp"]) else float(winner["original_price_gbp"]),
                "discount_price_gbp": None if pd.isna(winner["discount_price_gbp"]) else float(winner["discount_price_gbp"]),
            })
            if dry_run:
                print(
                    f"   [DRY-RUN] {row['product_code']} (£{row['base_price_gbp']:.2f}) 将对齐到"
                    f" {winner['product_code']} 的价格 (£{winner['base_price_gbp']:.2f} → "
                    f"¥{winner['jingya_untaxed_price']})  [共用渠道产品id={channel_id}]"
                )

    if updates and not dry_run:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE barbour_inventory
                SET base_price_gbp       = :base_price_gbp,
                    jingya_untaxed_price = :jingya_untaxed_price,
                    taobao_store_price   = :taobao_store_price,
                    source_price_gbp     = :source_price_gbp,
                    original_price_gbp   = :original_price_gbp,
                    discount_price_gbp   = :discount_price_gbp,
                    last_checked         = NOW()
                WHERE product_code = :product_code
            """), updates)

    return len(updates)


def write_codes_excel(codes, out_path: str, col_name: str = "商品编码") -> str:
    """
    把一批商品编码写成一个只有编码列的 Excel。

    用途：channels/jingya/export/ 下几个多品牌通用脚本（export_stock_excel 等）
    的 exclude_excel_file/白名单参数只认"列名含 code 或 编码"的 Excel，不关心
    其它内容——这个函数就是配合它们，把 Barbour 这边算出来的编码集合（比如
    "排除清单里没指定供应商、库存应该跳过导出"的那批）动态落成一个临时文件，
    不需要去改那些通用脚本本身。
    """
    codes = sorted({str(c).strip() for c in codes if str(c).strip()})
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({col_name: codes}).to_excel(out_file, index=False)
    return str(out_file)


def _eff_price_row(row) -> Optional[float]:
    """有效成本口径：sale_price_gbp（已含折扣策略+运费）优先，其次 price_gbp，最后 original_price_gbp。"""
    for v in (row.get("sale_price_gbp"), row.get("price_gbp"), row.get("original_price_gbp")):
        if v is not None and not pd.isna(v) and float(v) > 0:
            return float(v)
    return None


def _select_sites_by_price_window(
    cand: Optional[pd.DataFrame],
    price_tolerance_pct: float,
    max_suppliers: int,
    min_sizes_in_stock: int = 1,
) -> List[dict]:
    """
    价格窗口选站点：按有效成本从低到高排序，取成本最低的供应商为基准，
    凡是成本不超过"基准 × (1 + price_tolerance_pct)"的供应商都一并纳入
    （最多凑满 max_suppliers 家）。窗口外更贵的供应商一律不看——即使窗口
    内供应商合计的有货尺码数很少，也不会为了凑尺码去纳入窗口外的供应商。

    min_sizes_in_stock：初选门槛，有货尺码数低于此值的供应商直接从候选池
    剔除（包括不能作为最低价基准），避免"价格最低但几乎断货"的供应商
    单独垄断分配。若门槛把候选池筛空（没有任何供应商达标），回退为不设
    门槛，按原候选池继续选——避免商品因此被强制清零库存；调用方可通过
    返回值判断是否发生了回退（见 allocate_and_sync 里的诊断计数）。

    allocate_and_sync（批量）和 select_suppliers_for_code（单品预览）共用
    这一份实现，避免诊断工具和实际写库逻辑走两套算法、结果对不上。

    cand: 需含列 site_name / min_eff_price / sizes_in_stock / latest。
    """
    chosen: List[dict] = []
    if cand is None or cand.empty:
        return chosen

    pool = cand
    if min_sizes_in_stock > 1:
        filtered = cand[cand["sizes_in_stock"] >= min_sizes_in_stock]
        if not filtered.empty:
            pool = filtered
        # 否则：没有供应商达标，回退用未过滤的候选池（宁可库存浅，也不强制清零）。

    ranked = pool.sort_values(
        ["min_eff_price", "sizes_in_stock", "latest"],
        ascending=[True, False, False],
    )
    base_price = float(ranked.iloc[0]["min_eff_price"])
    threshold = base_price * (1 + price_tolerance_pct)

    for _, r in ranked.iterrows():
        if len(chosen) >= max_suppliers:
            break
        if float(r["min_eff_price"]) > threshold:
            break  # 已按成本升序排列，后面只会更贵
        chosen.append({
            "site": r["site_name"],
            "min_eff_price": float(r["min_eff_price"]),
            "sizes_in_stock": int(r["sizes_in_stock"]),
        })
    return chosen


def _select_sites_by_fill_sizes(
    cand: Optional[pd.DataFrame],
    sizes_by_site: Dict[str, Set[str]],
    target_sizes: int,
    max_suppliers: Optional[int] = None,
) -> List[dict]:
    """
    凑尺码选站点（策略二）：按有效成本从低到高逐家合并库存，合并后的有货
    尺码数（并集）达到 target_sizes 就停止。不能带来任何新尺码的供应商直接
    跳过——它只会抬高定价基准（取所选最贵者）却不增加库存。所有供应商都
    合并完仍不够 target_sizes，就用已合并的全部。

    不使用 min_sizes_in_stock 门槛：单尺码的低价供应商也能参与合并。
    sizes_by_site: site_name -> 该站点有货的 size_norm 集合。
    """
    chosen: List[dict] = []
    if cand is None or cand.empty:
        return chosen

    ranked = cand.sort_values(
        ["min_eff_price", "sizes_in_stock", "latest"],
        ascending=[True, False, False],
    )
    covered: Set[str] = set()
    for _, r in ranked.iterrows():
        if len(covered) >= target_sizes:
            break
        if max_suppliers and len(chosen) >= max_suppliers:
            break
        site_sizes = sizes_by_site.get(r["site_name"], set())
        if chosen and not (site_sizes - covered):
            continue  # 没有新尺码，跳过
        covered |= site_sizes
        chosen.append({
            "site": r["site_name"],
            "min_eff_price": float(r["min_eff_price"]),
            "sizes_in_stock": int(r["sizes_in_stock"]),
        })
    return chosen


def _select_sites(
    cand: Optional[pd.DataFrame],
    sizes_by_site: Dict[str, Set[str]],
    strategy: str,
    price_tolerance_pct: float,
    max_suppliers: int,
    min_sizes_in_stock: int,
    fill_target: int,
    fill_max_sites: Optional[int],
) -> List[dict]:
    """按 strategy 分派到对应的选站点算法；allocate_and_sync 和 select_suppliers_for_code 共用。"""
    if strategy == "price_window":
        return _select_sites_by_price_window(cand, price_tolerance_pct, max_suppliers, min_sizes_in_stock)
    if strategy == "fill_sizes":
        return _select_sites_by_fill_sizes(cand, sizes_by_site, fill_target, fill_max_sites)
    raise ValueError(f"未知的 SUPPLIER_STRATEGY：{strategy!r}（可选 'price_window' / 'fill_sizes'）")


# ═══════════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════════

def allocate_and_sync(
    brand: str = "barbour",
    price_tolerance_pct: Optional[float] = None,
    max_suppliers: Optional[int] = None,
    min_sizes_in_stock: Optional[int] = None,
    manual_stock_xlsx: Optional[str] = MANUAL_STOCK_XLSX,
    manual_price_xlsx: Optional[str] = MANUAL_PRICE_XLSX,
    dry_run: bool = False,
    strategy: Optional[str] = None,
) -> dict:
    """
    为所有已发布商品重新计算供应商组合 + 价格 + 库存，并同步到
    barbour_inventory + barbour_supplier_allocation。

    dry_run=True 时只打印将要发生的变更，不写库。
    manual_stock_xlsx：手动库存清单里"ID + 供货商"的行，该 ID 下所有颜色强制
    只用这个供货商（"只填 ID"的行只影响阶段 D 的库存导出，这里照常自动分配）。
    manual_price_xlsx：手动价格清单里填了价格的 ID，自动分配后用人工价覆盖；
    价格留空的 ID 不参与同款价格对齐（阶段 D 也不导出其价格）。
    两个文件不存在时自动忽略；传 None 可显式关闭。
    min_sizes_in_stock：初选供应商的最低有货尺码数门槛，默认取配置文件里
    的 SUPPLIER_MIN_SIZES_IN_STOCK；传参可临时覆盖（单次运行生效，不改
    配置文件）。
    """
    if brand.lower() != "barbour":
        raise ValueError("目前仅支持 barbour")

    price_tolerance_pct = price_tolerance_pct if price_tolerance_pct is not None else SUPPLIER_PRICE_TOLERANCE_PCT
    max_suppliers = max_suppliers if max_suppliers is not None else SUPPLIER_MAX_SITES
    min_sizes_in_stock = min_sizes_in_stock if min_sizes_in_stock is not None else SUPPLIER_MIN_SIZES_IN_STOCK
    strategy = strategy or SUPPLIER_STRATEGY
    print(f"🧮 供应商选择策略：{strategy}")

    engine = _get_engine()
    _skip_stock_ids, forced_site_by_id = load_manual_stock(manual_stock_xlsx)
    locked_ids, fixed_price_by_id = load_manual_price(manual_price_xlsx)
    by_id = codes_by_channel_id(set(forced_site_by_id) | locked_ids | set(fixed_price_by_id), engine)
    manual_overrides: Dict[str, str] = {
        code: site for cid, site in forced_site_by_id.items() for code in by_id.get(cid, set())
    }
    fixed_price_by_code: Dict[str, Tuple[Optional[float], Optional[float]]] = {
        code: prices for cid, prices in fixed_price_by_id.items() for code in by_id.get(cid, set())
    }
    pub_map = _load_publication_mappings(PUBLICATION_DIR)
    taobao_discount = TAOBAO_STORE_DISCOUNT

    if manual_overrides:
        print(f"🧭 手动库存指定供货商：{len(forced_site_by_id)} 个渠道商品ID（{len(manual_overrides)} 个颜色编码）。")
    if fixed_price_by_code:
        print(f"💷 手动固定价格：{len(fixed_price_by_id)} 个渠道商品ID（{len(fixed_price_by_code)} 个颜色编码）。")

    with engine.begin() as conn:
        conn.execute(SQL_CREATE_ALLOC)
        # 只是加列（ADD COLUMN IF NOT EXISTS），不改数据，dry_run 下也要跑，
        # 否则在全新数据库上首次 dry_run 会因为列不存在而查询失败。
        _ensure_price_columns(conn)

        inv_df = pd.read_sql(text("""
            SELECT id, product_code, size, stock_count,
                   base_price_gbp, jingya_untaxed_price, taobao_store_price
            FROM barbour_inventory
            WHERE is_published = TRUE
              AND product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """), conn)

        offers_df = pd.read_sql(text("""
            SELECT product_code, site_name, size, stock_count,
                   sale_price_gbp, price_gbp, original_price_gbp, last_checked
            FROM barbour_offers
            WHERE is_active = TRUE
              AND product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """), conn)

    if inv_df.empty:
        print("ℹ️ 没有已发布商品（barbour_inventory.is_published=TRUE 为空），已跳过。")
        return {"processed": 0}

    inv_df["size_norm"] = inv_df["size"].map(clean_size_for_barbour)
    offers_df["site_name"] = offers_df["site_name"].map(lambda s: canonical_site(s) or s)
    offers_df["size_norm"] = offers_df["size"].map(clean_size_for_barbour)
    offers_df["eff_price"] = offers_df.apply(_eff_price_row, axis=1)
    offers_df["in_stock"] = pd.to_numeric(offers_df["stock_count"], errors="coerce").fillna(0) > 0

    in_stock_df = offers_df[offers_df["in_stock"]]

    site_agg = (
        in_stock_df[in_stock_df["eff_price"].notna()]
        .groupby(["product_code", "site_name"])
        .agg(
            sizes_in_stock=("size_norm", "nunique"),
            min_eff_price=("eff_price", "min"),
            latest=("last_checked", "max"),
        )
        .reset_index()
    )
    site_agg_by_code = {code: g for code, g in site_agg.groupby("product_code")}

    # (product_code, site_name) -> 该站点有货的 size_norm 集合
    stock_sizes_map: Dict[Tuple[str, str], Set[str]] = (
        in_stock_df.groupby(["product_code", "site_name"])["size_norm"]
        .apply(set)
        .to_dict()
    )

    inv_by_code = {code: g for code, g in inv_df.groupby("product_code")}
    published_codes = sorted(inv_df["product_code"].unique().tolist())

    inventory_updates: List[dict] = []
    allocation_rows: List[dict] = []
    zero_stock_updates: List[dict] = []   # 无法分配供应商的商品：强制清零库存，防止超卖
    diag_unresolved: List[Tuple[str, str, str]] = []
    diag_unresolved_codes: List[str] = []
    diag_auto: List[str] = []
    diag_manual: List[str] = []
    dry_run_report: List[dict] = []
    dry_run_zero_report: List[dict] = []

    def _force_zero_stock(code: str) -> None:
        """
        没有任何达标供应商时，不能让 barbour_inventory 停在旧库存/占位库存上——
        必须显式把这个商品的所有尺码库存清零，避免鲸芽端仍显示有货、客户下单后
        我们却采购不到，导致淘宝售后处罚。只清库存，不动价格字段。
        """
        for _, inv_row in inv_by_code[code].iterrows():
            zero_stock_updates.append({"bi_id": int(inv_row["id"])})
            if dry_run:
                old_stock = int(inv_row.get("stock_count") or 0)
                if old_stock != 0:
                    dry_run_zero_report.append({
                        "product_code": code, "size": inv_row["size"], "旧库存": old_stock,
                    })

    for code in published_codes:
        forced_site = manual_overrides.get(code)
        cand = site_agg_by_code.get(code)

        chosen: List[dict] = []  # [{"site", "min_eff_price", "sizes_in_stock"}]
        source = "auto"

        if forced_site:
            source = "manual"
            if cand is not None:
                row = cand[cand["site_name"] == forced_site]
                if not row.empty:
                    r = row.iloc[0]
                    chosen = [{
                        "site": forced_site,
                        "min_eff_price": float(r["min_eff_price"]),
                        "sizes_in_stock": int(r["sizes_in_stock"]),
                    }]
            if not chosen:
                diag_unresolved.append((code, "人工指定供应商无有效报价", forced_site))
                diag_unresolved_codes.append(code)
                _force_zero_stock(code)
                continue
        else:
            sizes_by_site = (
                {s: stock_sizes_map.get((code, s), set()) for s in cand["site_name"]}
                if cand is not None else {}
            )
            chosen = _select_sites(
                cand,
                sizes_by_site,
                strategy,
                price_tolerance_pct,
                max_suppliers,
                min_sizes_in_stock,
                FILL_SIZES_TARGET,
                FILL_SIZES_MAX_SITES,
            )

            if not chosen:
                # 兜底：发布 Excel 里的历史供应商（新品还没抓到 offers 的情况）
                fallback_site = pub_map.get(code)
                if fallback_site:
                    fb_rows = offers_df[
                        (offers_df["product_code"] == code)
                        & (offers_df["site_name"] == fallback_site)
                        & offers_df["eff_price"].notna()
                    ]
                    # 定价只看有货的行，避免拿一个缺货尺码的低价当基准；
                    # 若这个站点当前一个尺码都没货，才退回用全部行估个价。
                    fb_in_stock = fb_rows[fb_rows["in_stock"]]
                    fb_price_rows = fb_in_stock if not fb_in_stock.empty else fb_rows
                    if not fb_price_rows.empty:
                        chosen = [{
                            "site": fallback_site,
                            "min_eff_price": float(fb_price_rows["eff_price"].min()),
                            "sizes_in_stock": int(fb_in_stock["size_norm"].nunique()),
                        }]

            if not chosen:
                diag_unresolved.append((code, "无达标供应商", ""))
                diag_unresolved_codes.append(code)
                _force_zero_stock(code)
                continue

        price_basis = max(c["min_eff_price"] for c in chosen)
        untaxed, retail = calculate_jingya_prices(price_basis)
        untaxed = round(float(untaxed), 2) if untaxed else 0.0
        retail_tb = round(float(retail) * float(taobao_discount), 2) if retail else 0.0

        covered_sizes: Set[str] = set()
        for c in chosen:
            covered_sizes |= stock_sizes_map.get((code, c["site"]), set())

        (diag_manual if source == "manual" else diag_auto).append(code)

        for i, c in enumerate(chosen, start=1):
            allocation_rows.append({
                "product_code": code,
                "site_name": c["site"],
                "rank": i,
                "min_eff_price": c["min_eff_price"],
                "sizes_in_stock": c["sizes_in_stock"],
                "is_price_basis": c["min_eff_price"] == price_basis,
                "source": source,
            })

        primary_site = chosen[0]["site"]
        for _, inv_row in inv_by_code[code].iterrows():
            new_stock = DEFAULT_STOCK_COUNT if inv_row["size_norm"] in covered_sizes else 0
            inventory_updates.append({
                "bi_id": int(inv_row["id"]),
                "stock_count": new_stock,
                "source_site": primary_site,
                "source_price_gbp": price_basis,
                "original_price_gbp": price_basis,
                "discount_price_gbp": price_basis,
                "base_price_gbp": price_basis,
                "jingya_untaxed_price": untaxed,
                "taobao_store_price": retail_tb,
            })
            if dry_run:
                old_price = inv_row.get("jingya_untaxed_price")
                old_stock = inv_row.get("stock_count")
                old_price_f = None if pd.isna(old_price) else float(old_price)
                if old_price_f != untaxed or int(old_stock or 0) != new_stock:
                    dry_run_report.append({
                        "product_code": code, "size": inv_row["size"],
                        "旧库存": old_stock, "新库存": new_stock,
                        "旧未税价": old_price_f, "新未税价": untaxed,
                        "供应商组合": "+".join(c["site"] for c in chosen),
                    })

    # ── 打印诊断 ──
    print(
        f"✅ 自动分配：{len(diag_auto)} 个；手动指定供货商：{len(diag_manual)} 个；"
        f"无法分配：{len(diag_unresolved)} 个。"
    )
    if diag_unresolved:
        print(f"⚠️ 以下 {len(diag_unresolved)} 个商品本次未能分配供应商（库存已强制清零，避免超卖/淘宝处罚；价格字段保持不变）：")
        for code, reason, extra in diag_unresolved[:30]:
            print(f"   {code}: {reason} {extra}".rstrip())
        if len(diag_unresolved) > 30:
            print(f"   ...共 {len(diag_unresolved)} 个，已省略 {len(diag_unresolved) - 30} 个")

    no_reconcile_ids = locked_ids | set(fixed_price_by_id)

    if dry_run:
        print(f"\n[DRY-RUN] 将变更 {len(dry_run_report)} 条尺码记录（未写库）。示例前 20 条：")
        for r in dry_run_report[:20]:
            print(f"   {r}")
        if dry_run_zero_report:
            print(f"\n[DRY-RUN] 无达标供应商、库存将被强制清零的尺码记录共 {len(dry_run_zero_report)} 条。示例前 20 条：")
            for r in dry_run_zero_report[:20]:
                print(f"   {r}")
        _apply_fixed_prices(engine, fixed_price_by_code, dry_run=True)
        print("\n[DRY-RUN] 同款多颜色共用鲸芽 channel_product_id 的价格对齐预览：")
        reconciled_preview = _reconcile_shared_channel_prices(engine, dry_run=True, locked_ids=no_reconcile_ids)
        if reconciled_preview == 0:
            print("   （当前没有需要对齐的分叉价格）")
        return {
            "processed": len(diag_auto) + len(diag_manual),
            "unresolved": len(diag_unresolved),
            "would_change": len(dry_run_report),
            "would_force_zero_stock": len(dry_run_zero_report),
            "would_reconcile_channel_prices": reconciled_preview,
        }

    # ── 写库 ──
    processed_codes = list(set(diag_auto) | set(diag_manual))
    with engine.begin() as conn:
        if inventory_updates:
            conn.execute(text("""
                UPDATE barbour_inventory
                SET stock_count = :stock_count,
                    source_site = :source_site,
                    source_price_gbp = :source_price_gbp,
                    original_price_gbp = :original_price_gbp,
                    discount_price_gbp = :discount_price_gbp,
                    base_price_gbp = :base_price_gbp,
                    jingya_untaxed_price = :jingya_untaxed_price,
                    taobao_store_price = :taobao_store_price,
                    last_checked = NOW()
                WHERE id = :bi_id
            """), inventory_updates)

        if zero_stock_updates:
            # 无达标供应商：只清库存，不动价格字段（价格字段此时多为占位 NULL 或
            # 上一次的历史值，留着不影响——反正 0 库存已经杜绝了超卖风险）。
            conn.execute(text("""
                UPDATE barbour_inventory
                SET stock_count = 0,
                    last_checked = NOW()
                WHERE id = :bi_id
            """), zero_stock_updates)

        if diag_unresolved_codes:
            # 清掉这些编码在 barbour_supplier_allocation 里可能残留的旧分配记录，
            # 避免报表/诊断工具显示一个早已不成立的"供应商组合"。
            conn.execute(
                text(f"DELETE FROM {TABLE_ALLOC} WHERE product_code = ANY(:codes)"),
                {"codes": diag_unresolved_codes},
            )

        if processed_codes:
            conn.execute(
                text(f"DELETE FROM {TABLE_ALLOC} WHERE product_code = ANY(:codes)"),
                {"codes": processed_codes},
            )
        if allocation_rows:
            conn.execute(text(f"""
                INSERT INTO {TABLE_ALLOC}
                    (product_code, site_name, rank, min_eff_price, sizes_in_stock, is_price_basis, source, updated_at)
                VALUES
                    (:product_code, :site_name, :rank, :min_eff_price, :sizes_in_stock, :is_price_basis, :source, NOW())
            """), allocation_rows)

    print(
        f"✅ barbour_inventory 已更新 {len(inventory_updates)} 条尺码记录（另有 "
        f"{len(zero_stock_updates)} 条因无达标供应商被强制清零）；"
        f"{TABLE_ALLOC} 已写入 {len(allocation_rows)} 条供应商分配记录。"
    )

    # ── 手动价格清单覆盖（最终层）──
    _apply_fixed_prices(engine, fixed_price_by_code, dry_run=False)

    # ── 同款多颜色共用鲸芽 channel_product_id 时，价格对齐到组内最高者 ──
    # 手动价格清单里的 ID（锁价 / 固定价）不参与对齐。
    reconciled = _reconcile_shared_channel_prices(engine, dry_run=False, locked_ids=no_reconcile_ids)
    if reconciled:
        print(f"✅ 同款多颜色价格分叉已对齐：{reconciled} 个 product_code 的价格已同步为组内最高价。")

    return {
        "processed": len(processed_codes),
        "unresolved": len(diag_unresolved),
        "inventory_rows_updated": len(inventory_updates),
        "inventory_rows_zeroed": len(zero_stock_updates),
        "allocation_rows": len(allocation_rows),
        "reconciled_channel_prices": reconciled,
    }


# ═══════════════════════════════════════════════════════════════════
#  单商品预览（供 tool_inspect_supplier.py 等诊断脚本调用，不写库）
# ═══════════════════════════════════════════════════════════════════

def select_suppliers_for_code(
    code: str,
    price_tolerance_pct: Optional[float] = None,
    max_suppliers: Optional[int] = None,
    min_sizes_in_stock: Optional[int] = None,
    strategy: Optional[str] = None,
) -> dict:
    """
    对单个商品跑一遍与 allocate_and_sync 相同的供应商选择算法（按 strategy），只返回结果、不写库。
    返回 {"chosen": [{"site","min_eff_price","sizes_in_stock"}, ...],
          "covered_sizes": set(size_norm), "price_basis": float | None}
    """
    price_tolerance_pct = price_tolerance_pct if price_tolerance_pct is not None else SUPPLIER_PRICE_TOLERANCE_PCT
    max_suppliers = max_suppliers if max_suppliers is not None else SUPPLIER_MAX_SITES
    min_sizes_in_stock = min_sizes_in_stock if min_sizes_in_stock is not None else SUPPLIER_MIN_SIZES_IN_STOCK

    engine = _get_engine()
    with engine.connect() as conn:
        offers_df = pd.read_sql(
            text("""
                SELECT site_name, size, stock_count,
                       sale_price_gbp, price_gbp, original_price_gbp, last_checked
                FROM barbour_offers
                WHERE product_code = :code AND is_active = TRUE
            """),
            conn, params={"code": code},
        )

    if offers_df.empty:
        return {"chosen": [], "covered_sizes": set(), "price_basis": None}

    offers_df["site_name"] = offers_df["site_name"].map(lambda s: canonical_site(s) or s)
    offers_df["size_norm"] = offers_df["size"].map(clean_size_for_barbour)
    offers_df["eff_price"] = offers_df.apply(_eff_price_row, axis=1)
    offers_df["in_stock"] = pd.to_numeric(offers_df["stock_count"], errors="coerce").fillna(0) > 0

    in_stock_df = offers_df[offers_df["in_stock"]]
    site_agg = (
        in_stock_df[in_stock_df["eff_price"].notna()]
        .groupby("site_name")
        .agg(
            sizes_in_stock=("size_norm", "nunique"),
            min_eff_price=("eff_price", "min"),
            latest=("last_checked", "max"),
        )
        .reset_index()
    )
    stock_sizes_map = in_stock_df.groupby("site_name")["size_norm"].apply(set).to_dict()

    chosen = _select_sites(
        site_agg,
        stock_sizes_map,
        strategy or SUPPLIER_STRATEGY,
        price_tolerance_pct,
        max_suppliers,
        min_sizes_in_stock,
        FILL_SIZES_TARGET,
        FILL_SIZES_MAX_SITES,
    )
    covered: Set[str] = set()
    for c in chosen:
        covered |= stock_sizes_map.get(c["site"], set())

    price_basis = max((c["min_eff_price"] for c in chosen), default=None)
    return {"chosen": chosen, "covered_sizes": covered, "price_basis": price_basis}


# ═══════════════════════════════════════════════════════════════════
#  手动价格清单覆盖
# ═══════════════════════════════════════════════════════════════════

def _apply_fixed_prices(
    engine: Engine,
    fixed_price_by_code: Dict[str, Tuple[Optional[float], Optional[float]]],
    dry_run: bool = False,
) -> int:
    """
    手动价格清单覆盖：按 product_code 覆盖所有尺码行的价格字段。
    fixed_price_by_code: code -> (source_price_gbp, discount_price_gbp)，至少一个非空。

    定价基准 base = discount_price_gbp（空则 source_price_gbp），更新：
      source_price_gbp / discount_price_gbp / original_price_gbp（= 折扣价，空则保留原值）
      base_price_gbp / jingya_untaxed_price / taobao_store_price（由 calculate_jingya_prices 计算）
    库存与 source_site 不动（库存来源由手动库存清单/自动分配决定）。
    """
    if not fixed_price_by_code:
        return 0

    payload = []
    for code, (src, disc) in sorted(fixed_price_by_code.items()):
        base = disc if disc is not None else src
        untaxed, retail = calculate_jingya_prices(float(base))
        payload.append({
            "product_code": code,
            "source_price_gbp": src,
            "discount_price_gbp": disc,
            "original_price_gbp": disc,
            "base_price_gbp": base,
            "jingya_untaxed_price": round(float(untaxed), 2) if untaxed is not None else None,
            "taobao_store_price": round(float(retail) * float(TAOBAO_STORE_DISCOUNT), 2) if retail is not None else None,
        })

    if dry_run:
        print(f"\n[DRY-RUN] 手动价格将覆盖 {len(payload)} 个 product_code（所有尺码行）。示例前 5 条：")
        for x in payload[:5]:
            print(f"   {x}")
        return len(payload)

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE barbour_inventory
            SET source_price_gbp     = :source_price_gbp,
                original_price_gbp   = COALESCE(:original_price_gbp, original_price_gbp),
                discount_price_gbp   = :discount_price_gbp,
                base_price_gbp       = :base_price_gbp,
                jingya_untaxed_price = :jingya_untaxed_price,
                taobao_store_price   = :taobao_store_price,
                last_checked         = NOW()
            WHERE product_code = :product_code
        """), payload)

    print(f"✅ 手动价格已回填到 barbour_inventory：{len(payload)} 个 product_code（覆盖所有尺码行）。")
    return len(payload)


# ═══════════════════════════════════════════════════════════════════
#  人可读报表：每个商品当前售价 / 折扣率 / 库存 / 供货商（只读，不写库）
# ═══════════════════════════════════════════════════════════════════

def export_price_stock_supplier_report(output_path: Optional[str] = None) -> str:
    """
    导出一份人可读的 Excel：每行一个已发布商品，列出：
      - 商品名称/颜色（来自 barbour_products.style_name/color；
        barbour_inventory.product_title 这一列对 barbour 一直是空的，
        不能用，sku_name 也只是"编码，尺码"拼接串，不是真正的商品名）
      - 当前用哪几家供货商（按 barbour_supplier_allocation 的 rank 拼接）
      - 定价依据供货商（is_price_basis=TRUE 的那家，即成本最高、决定最终售价的那家）
      - 该供货商当前的促销折扣率（来自 barbour_offers.discount_pct）
      - 鲸芽未税价 / 淘宝零售价（barbour_inventory 当前值）
      - 库存（有货尺码数/总尺码数 + 具体有货尺码列表）
      - 最近更新时间

    纯查询导出，不做任何计算或写库；数据就是当前数据库里的实际状态。
    像 MWX0007OL71 这种在排除清单里没填供货商、一直没被自动分配触碰过的
    商品，这里会显示"供货商组合"为空、价格为空——报表本身就是排查这类
    遗漏的工具。
    """
    engine = _get_engine()
    with engine.connect() as conn:
        inv = pd.read_sql(text("""
            SELECT product_code,
                   COUNT(*)                                                            AS total_sizes,
                   COUNT(*) FILTER (WHERE stock_count > 0)                             AS in_stock_sizes,
                   STRING_AGG(size, ',' ORDER BY size) FILTER (WHERE stock_count > 0)   AS sizes_in_stock,
                   MAX(base_price_gbp)                                                 AS base_price_gbp,
                   MAX(jingya_untaxed_price)                                           AS jingya_untaxed_price,
                   MAX(taobao_store_price)                                             AS taobao_store_price,
                   MAX(last_checked)                                                   AS last_checked
            FROM barbour_inventory
            WHERE is_published = TRUE
            GROUP BY product_code
        """), conn)

        alloc = pd.read_sql(text(f"""
            SELECT product_code, site_name, rank, min_eff_price, is_price_basis, source
            FROM {TABLE_ALLOC}
            ORDER BY product_code, rank
        """), conn)

        offer_discount = pd.read_sql(text("""
            SELECT product_code, site_name,
                   MAX(discount_pct) FILTER (WHERE stock_count > 0) AS discount_pct
            FROM barbour_offers
            WHERE is_active = TRUE
            GROUP BY product_code, site_name
        """), conn)

        # 同一 product_code 在 barbour_products 里每个尺码一行，但 style_name/color
        # 是重复的，取任意一行即可（按 id 升序取第一行，结果稳定）。
        products = pd.read_sql(text("""
            SELECT DISTINCT ON (product_code) product_code, style_name, color
            FROM barbour_products
            ORDER BY product_code, id
        """), conn)

    if inv.empty:
        print("ℹ️ barbour_inventory 里没有已发布商品，未生成报表。")
        return ""

    out = inv.merge(products, on="product_code", how="left")

    if not alloc.empty:
        combo = (
            alloc.groupby("product_code")["site_name"]
            .apply(lambda s: "+".join(s))
            .rename("供货商组合")
        )
        out = out.merge(combo, on="product_code", how="left")

        basis = alloc[alloc["is_price_basis"]][["product_code", "site_name", "min_eff_price", "source"]].rename(
            columns={"site_name": "定价依据供货商", "min_eff_price": "供货商成本价(£)", "source": "分配来源"}
        )
        if not offer_discount.empty:
            basis = basis.merge(
                offer_discount.rename(columns={"site_name": "定价依据供货商", "discount_pct": "折扣率(%)"}),
                on=["product_code", "定价依据供货商"], how="left",
            )
        else:
            basis["折扣率(%)"] = None
        out = out.merge(basis, on="product_code", how="left")
    else:
        for col in ("供货商组合", "定价依据供货商", "分配来源", "供货商成本价(£)", "折扣率(%)"):
            out[col] = None

    out["库存"] = out["in_stock_sizes"].fillna(0).astype(int).astype(str) + "/" + out["total_sizes"].astype(int).astype(str)

    out = out.rename(columns={
        "product_code": "商品编码",
        "style_name": "商品名称",
        "color": "颜色",
        "sizes_in_stock": "有货尺码",
        "base_price_gbp": "定价基准(£)",
        "jingya_untaxed_price": "鲸芽未税价(¥)",
        "taobao_store_price": "淘宝零售价(¥)",
        "last_checked": "最近更新",
    })

    cols = [
        "商品编码", "商品名称", "颜色",
        "供货商组合", "定价依据供货商", "分配来源",
        "供货商成本价(£)", "折扣率(%)", "定价基准(£)",
        "鲸芽未税价(¥)", "淘宝零售价(¥)",
        "库存", "有货尺码", "最近更新",
    ]
    out = out[cols].sort_values("商品编码").reset_index(drop=True)

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(BARBOUR["OUTPUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = out_dir / f"barbour_price_stock_supplier_report_{ts}.xlsx"

    out.to_excel(out_file, index=False)
    no_supplier = int((out["供货商组合"].isna() | (out["供货商组合"] == "")).sum())
    print(f"✅ 报表已导出：{out_file}（{len(out)} 个商品，其中 {no_supplier} 个无供货商分配记录）。")
    return str(out_file)


# ═══════════════════════════════════════════════════════════════════
#  CLI：
#    python -m brands.barbour.jingya.allocate_supplier_and_price            → dry-run 预览
#    python -m brands.barbour.jingya.allocate_supplier_and_price --apply    → 真正写库
#    python -m brands.barbour.jingya.allocate_supplier_and_price --report   → 只导出报表，不分配
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if "--report" in sys.argv:
        export_price_stock_supplier_report()
    else:
        apply = "--apply" in sys.argv
        allocate_and_sync(dry_run=not apply)
