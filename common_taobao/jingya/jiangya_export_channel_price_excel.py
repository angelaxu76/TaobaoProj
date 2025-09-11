# jiangya_export_channel_price_excel.py
"""
通用导出：鲸芽 渠道价格更新 Excel（不读模板；固定 sheet 与表头；分文件）
- 函数签名不变：export_jiangya_channel_prices(brand: str, output_dir: Optional[str] = None) -> str
- 仅导出 channel_product_id 非空；每个渠道商品一行（按 channel_product_id 聚合）
- Base Price = min(original_price_gbp, discount_price_gbp)（存在者择其一）× BRAND_DISCOUNT[brand]（默认 1.0）
- 跳过下架/无价：Base Price 非法（NaN/<=0）不写入 Excel
- 定价：price_utils.calculate_jingya_prices(base_price, delivery_cost=7, exchange_rate=9.7)
    渠道价格(未税)(元)(必填) ← untaxed
    最低建议零售价(元)       ← retail
    最高建议零售价(元)       ← retail
- SKU ID 固定写 0
- 分包写出：每个文件最多 480 条数据行（不含表头），文件名末尾附 part 序号
"""

from pathlib import Path
from typing import Optional, List, Tuple
import math

import pandas as pd
import openpyxl
import psycopg2

from config import BRAND_CONFIG
try:
    from config import PGSQL_CONFIG  # 兜底
except Exception:
    PGSQL_CONFIG = {}

# 价格工具
try:
    from price_utils import calculate_jingya_prices
except Exception:
    # 若你的工程里在其它路径，可替换为实际导入
    from common_taobao.core.price_utils import calculate_jingya_prices  # type: ignore

# 固定 sheet 与表头
SHEET_NAME = "sheet1"
HEADERS = [
    "渠道产品ID",
    "SKU ID(不存在或者设置品价格时,sku填写0)",
    "渠道价格(未税)(元)(必填)",
    "最低建议零售价(元)",
    "最高建议零售价(元)",
]

# 品牌默认折扣
BRAND_DISCOUNT = {
    "camper": 0.71,
    "geox": 0.85,
    "clarks_jingya": 1.0,
    # 其它品牌默认 1.0
}

def _brand_discount(brand: str) -> float:
    return float(BRAND_DISCOUNT.get(brand.lower().strip(), 1.0))

def _to_float_safe(x) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except Exception:
        return 0.0

def _compute_base_price(row: pd.Series, brand: str) -> float:
    """Base = min(original, discount)（存在者择其一）× 品牌折扣；无值则 0"""
    o = _to_float_safe(row.get("original_price_gbp"))
    d = _to_float_safe(row.get("discount_price_gbp"))
    if o > 0 and d > 0:
        base_raw = min(o, d)
    else:
        base_raw = d if d > 0 else o
    return base_raw * _brand_discount(brand)

def _is_valid_price(x) -> bool:
    try:
        v = float(x)
        return (not math.isnan(v)) and (not math.isinf(v)) and (v > 0)
    except Exception:
        return False

def _write_one_excel(df_chunk: pd.DataFrame, file_path: Path):
    """按固定 sheet 和表头写一个 Excel（不依赖模板）"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    # 表头
    for c_idx, h in enumerate(HEADERS, start=1):
        ws.cell(row=1, column=c_idx, value=h)
    # 数据
    for r_idx, row in enumerate(df_chunk.itertuples(index=False), start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)
    wb.save(file_path)
    wb.close()

def export_jiangya_channel_prices(brand: str, output_dir: Optional[str] = None) -> str:
    """
    Pipeline 入口（签名保持不变）。
    返回第一个生成的文件路径；控制台会打印所有分包文件路径与行数。
    """
    brand_l = brand.lower().strip()
    if brand_l not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}。已配置品牌：{', '.join(sorted(BRAND_CONFIG.keys()))}")

    cfg = BRAND_CONFIG[brand_l]
    table = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)
    if not pgcfg:
        raise RuntimeError("PGSQL 连接配置缺失，请在 config.py 中提供 PGSQL_CONFIG 或品牌级 PGSQL_CONFIG。")

    # 1) 取数：仅 channel_product_id 非空/非空串
    conn = psycopg2.connect(
        host=pgcfg["host"], port=pgcfg["port"],
        user=pgcfg["user"], password=pgcfg["password"], dbname=pgcfg["dbname"],
    )
    sql = f"""
        SELECT channel_product_id,
               product_code,
               original_price_gbp,
               discount_price_gbp
        FROM {table}
        WHERE channel_product_id IS NOT NULL AND TRIM(channel_product_id) <> ''
    """
    df = pd.read_sql(sql, conn)
    conn.close()

    if df.empty:
        # 没有数据直接写出空表（仅表头）
        out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{brand_l}_jiangya_price_update_part1_of1.xlsx"
        empty_df = pd.DataFrame(columns=HEADERS)
        _write_one_excel(empty_df, out_file)
        print(f"[INFO] 无可导出的记录，生成空表：{out_file}")
        return str(out_file)

    # 2) 聚合：一行一个渠道商品
    df_grp = df.groupby("channel_product_id", dropna=False).agg({
        "product_code": "first",
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
    }).reset_index()

    # 3) Base Price & 过滤无效（下架/无价）
    df_grp["Base Price"] = df_grp.apply(lambda r: _compute_base_price(r, brand_l), axis=1)
    before = len(df_grp)
    df_grp = df_grp[df_grp["Base Price"].apply(_is_valid_price)].copy()
    skipped = before - len(df_grp)
    if skipped > 0:
        print(f"[INFO] 跳过无效/下架商品 {skipped} 行（Base Price 非法）。")

    if df_grp.empty:
        out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{brand_l}_jiangya_price_update_part1_of1.xlsx"
        empty_df = pd.DataFrame(columns=HEADERS)
        _write_one_excel(empty_df, out_file)
        print(f"[INFO] 过滤后无数据，生成空表：{out_file}")
        return str(out_file)

    # 4) 定价（untaxed, retail）
    def _safe_calc(p):
        p = _to_float_safe(p)
        try:
            return calculate_jingya_prices(p, delivery_cost=7, exchange_rate=9.7)
        except Exception as e:
            print(f"❌ calculate_jingya_prices 错误: base_price={p}, 错误: {e}")
            return (0, 0)

    prices = df_grp["Base Price"].apply(_safe_calc)
    expanded = prices.apply(pd.Series).fillna(0)
    expanded.columns = ["untaxed", "retail"]

    # 5) 组装导出数据（严格按列名顺序）
    out_df = pd.DataFrame({
        "渠道产品ID": df_grp["channel_product_id"].astype(str),
        "SKU ID(不存在或者设置品价格时,sku填写0)": 0,
        "渠道价格(未税)(元)(必填)": expanded["untaxed"].astype(int),
        "最低建议零售价(元)": expanded["retail"].astype(int),
        "最高建议零售价(元)": expanded["retail"].astype(int),
    })[HEADERS]

    # 6) 分包写出：每个文件最多 480 条数据行（不含表头）
    out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_size = 480
    n = len(out_df)
    num_parts = (n + chunk_size - 1) // chunk_size if n > 0 else 1
    created_files: List[Path] = []

    if n == 0:
        out_file = out_dir / f"{brand_l}_jiangya_price_update_part1_of1.xlsx"
        _write_one_excel(out_df, out_file)
        print(f"[INFO] 无有效记录，已生成空表：{out_file}")
        return str(out_file)

    for i in range(num_parts):
        start = i * chunk_size
        end = min(start + chunk_size, n)
        df_chunk = out_df.iloc[start:end].reset_index(drop=True)
        out_file = out_dir / f"{brand_l}_jiangya_price_update_part{i+1}_of_{num_parts}.xlsx"
        _write_one_excel(df_chunk, out_file)
        created_files.append(out_file)
        print(f"[OK] 写出：{out_file}（行数：{len(df_chunk)}）")

    # 返回第一个文件路径（保持签名/返回类型不变）
    return str(created_files[0])


# CLI（可选）
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出鲸芽渠道价格更新 Excel（固定表头/分文件）")
    parser.add_argument("--brand", required=True, help="品牌名，例如 camper / clarks_jingya / geox / barbour")
    parser.add_argument("--output-dir", default=None, help="可选，导出目录（默认 BRAND_CONFIG[brand]['OUTPUT_DIR']）")
    args = parser.parse_args()
    path = export_jiangya_channel_prices(args.brand, args.output_dir)
    print("[OK]", path)
