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

from pathlib import Path
from typing import Optional, List, Tuple
import pandas as pd
import openpyxl
import psycopg2

from config import BRAND_CONFIG, BASE_DIR  # 新增: BASE_DIR 用来拼默认路径
try:
    from config import PGSQL_CONFIG  # 兜底
except Exception:
    PGSQL_CONFIG = {}

SHEET_NAME_PRICE = "sheet1"
HEADERS_PRICE = ["渠道产品ID(必填)", "skuID", "渠道价格(未税)(元)(必填)", "最低建议零售价(元)", "最高建议零售价(元)"]

def _write_simple_excel(df: pd.DataFrame, file_path: Path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME_PRICE
    # 表头
    for c, h in enumerate(HEADERS_PRICE, start=1):
        ws.cell(row=1, column=c, value=h)
    # 数据
    for r_idx, row in enumerate(df.itertuples(index=False), start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)
    wb.save(file_path)
    wb.close()

def _load_exclude_codes(file_path: Path) -> List[str]:
    codes = []
    if not file_path.exists():
        print(f"[WARN] 排除清单未找到：{file_path}（将不做排除）")
        return codes
    for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        codes.append(s.upper())
    print(f"[INFO] 已加载排除编码 {len(codes)} 条。")
    return codes

def export_barbour_channel_price_by_sku(
    brand: str = "barbour",
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
    chunk_size: int = 490,
    strict: bool = True,  # True：发现空字段直接报错；False：跳过空行并仅告警
    exclude_codes_file: Optional[str] = None,  # 新增：排除清单路径
) -> str:
    """
    逐个 SKU 导出价格（Barbour 专用，不做任何价格计算，直接用 inventory 里的结果）
    导出列：渠道产品ID(必填), skuID, 渠道价格(未税)(元)(必填), 最低建议零售价(元), 最高建议零售价(元)

    规则：
    - channel_product_id 可重复；每个 skuid 必须存在
    - 若发现以下任一字段为空：channel_product_id / skuid / jingya_price_rmb / taobao_price_rmb
      则打印告警清单；strict=True 时抛错终止，strict=False 时跳过该行继续导出
    - 支持排除清单：exclude_codes.txt 中列出的 product_code 全部过滤（对应所有 skuid 都不导出）
    - 每个文件最多 chunk_size 条数据行（默认 490）
    返回：第一个导出文件路径
    """
    brand_l = brand.lower().strip()
    if brand_l not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}。可用：{', '.join(sorted(BRAND_CONFIG.keys()))}")

    cfg = BRAND_CONFIG[brand_l]
    table = cfg["TABLE_NAME"]  # barbour_inventory
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)
    if not pgcfg:
        raise RuntimeError("PGSQL 连接配置缺失，请在 config.py 中提供 PGSQL_CONFIG 或品牌级 PGSQL_CONFIG。")

    # 默认排除清单路径（D:/TB/Products/barbour/document/exclude_codes.txt）
    if exclude_codes_file is None:
        # BASE_DIR/barbour/document/exclude_codes.txt
        default_exclude = Path(BASE_DIR) / "barbour" / "document" / "exclude_codes.txt"
    else:
        default_exclude = Path(exclude_codes_file)

    exclude_codes = set(_load_exclude_codes(default_exclude))

    # 连接
    conn = psycopg2.connect(
        host=pgcfg["host"], port=pgcfg["port"],
        user=pgcfg["user"], password=pgcfg["password"], dbname=pgcfg["dbname"],
    )
    # 注意：为实现“按 product_code 排除”，这里把 product_code 一并查出来
    sql = f"""
        SELECT
            channel_product_id,
            skuid,
            product_code,
            jingya_price_rmb,
            taobao_price_rmb
        FROM {table}
        WHERE channel_product_id IS NOT NULL
          AND TRIM(channel_product_id) <> ''
    """
    df = pd.read_sql(sql, conn)
    conn.close()

    # 空表处理
    out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(filename).stem if filename else f"{brand_l}_jiangya_channel_price_sku"

    if df.empty:
        out_file = out_dir / f"{base}_part1_of1.xlsx"
        _write_simple_excel(pd.DataFrame(columns=HEADERS_PRICE), out_file)
        print(f"[INFO] 无可导出的记录，生成空表：{out_file}")
        return str(out_file)

    # 规范化
    for col in ("channel_product_id", "skuid", "product_code"):
        df[col] = df[col].astype(str).str.strip()

    # 按排除清单过滤（大小写不敏感：统一转大写比对）
    if exclude_codes:
        before = len(df)
        df = df[~df["product_code"].str.upper().isin(exclude_codes)].reset_index(drop=True)
        removed = before - len(df)
        print(f"[INFO] 已按排除清单过滤 {removed} 行。")

    # 转数字
    def to_num(s):
        try:
            return float(s)
        except Exception:
            return None

    df["jingya_price_rmb"] = df["jingya_price_rmb"].apply(to_num)
    df["taobao_price_rmb"] = df["taobao_price_rmb"].apply(to_num)

    # 关键字段校验
    issues: List[Tuple[int, str]] = []
    mask_missing = (
        (df["channel_product_id"] == "") |
        (df["skuid"] == "") |
        (df["jingya_price_rmb"].isna()) |
        (df["taobao_price_rmb"].isna())
    )
    if mask_missing.any():
        bad = df[mask_missing].copy()
        for idx, row in bad.iterrows():
            issues.append((
                idx,
                f"缺失字段 -> code='{row.get('product_code', '')}', "
                f"cpid='{row.get('channel_product_id', '')}', "
                f"skuid='{row.get('skuid', '')}', "
                f"jingya='{row.get('jingya_price_rmb', '')}', "
                f"taobao='{row.get('taobao_price_rmb', '')}'"
            ))
        print("[WARN] 发现字段缺失的记录：")
        for i in issues:
            print("   - 行", i[0], i[1])
        if strict:
            raise ValueError(f"存在 {len(issues)} 条缺失关键字段的记录；已列出详情。请先修复后再导出。")
        # 非严格模式：跳过有问题的行
        df = df[~mask_missing].reset_index(drop=True)




    # === 在此处插入：为每个渠道产品ID补一行 skuID=0 的“品价格”（取该商品价格中最高值） ===
    # 1) 只保留导出所需列（避免带入 product_code）
    df_use = df[["channel_product_id", "skuid", "jingya_price_rmb", "taobao_price_rmb"]].copy()

    # 2) 统计每个渠道产品ID的最高价（jingya、taobao 各自取最高）
    agg_max = (
        df_use.groupby("channel_product_id", as_index=False)
              .agg(max_j=("jingya_price_rmb", "max"),
                   max_t=("taobao_price_rmb", "max"))
    )

    # 3) 生成 skuID=0 的“品价格”行
    zero_rows = agg_max.assign(
        skuid="0",
        jingya_price_rmb=lambda x: x["max_j"],
        taobao_price_rmb=lambda x: x["max_t"]
    )[["channel_product_id", "skuid", "jingya_price_rmb", "taobao_price_rmb"]]

    # 4) 原始明细去掉已存在的 skuID=0，避免重复
    detail_rows = df_use[df_use["skuid"] != "0"]

    # 5) 合并，并设置排序：同一渠道产品ID里，skuID=0 放最前，再按 skuid 升序
    df_for_export = pd.concat([zero_rows, detail_rows], ignore_index=True)
    df_for_export["zero_first"] = (df_for_export["skuid"] != "0").astype(int)
    df_for_export = df_for_export.sort_values(
        by=["channel_product_id", "zero_first", "skuid"]
    ).drop(columns=["zero_first"]).reset_index(drop=True)


    # 组织导出列
    out_df = pd.DataFrame({
        "渠道产品ID(必填)": df_for_export["channel_product_id"],
        "skuID": df_for_export["skuid"],
        "渠道价格(未税)(元)(必填)": df_for_export["jingya_price_rmb"].round(2),
        "最低建议零售价(元)": df_for_export["taobao_price_rmb"].round(2),
        "最高建议零售价(元)": df_for_export["taobao_price_rmb"].round(2),
    })[HEADERS_PRICE]

    # 👉 按渠道产品ID排序
    out_df = out_df.sort_values(by=["渠道产品ID(必填)", "skuID"]).reset_index(drop=True)
    

    # 分包写出
    n = len(out_df)
    if n == 0:
        out_file = out_dir / f"{base}_part1_of1.xlsx"
        _write_simple_excel(out_df, out_file)
        print(f"[INFO] 过滤后无有效记录，已生成空表：{out_file}")
        return str(out_file)

    num_parts = (n + chunk_size - 1) // chunk_size
    created: List[Path] = []
    for i in range(num_parts):
        start, end = i * chunk_size, min((i + 1) * chunk_size, n)
        chunk = out_df.iloc[start:end].reset_index(drop=True)
        out_file = out_dir / (f"{base}.xlsx" if num_parts == 1 and filename else f"{base}_part{i+1}_of_{num_parts}.xlsx")
        _write_simple_excel(chunk, out_file)
        created.append(out_file)
        print(f"[OK] 写出：{out_file}（行数：{len(chunk)}）")

    return str(created[0])


# CLI（可选）
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出鲸芽渠道价格更新 Excel（固定表头/分文件）")
    parser.add_argument("--brand", required=True, help="品牌名，例如 camper / clarks_jingya / geox / barbour")
    parser.add_argument("--output-dir", default=None, help="可选，导出目录（默认 BRAND_CONFIG[brand]['OUTPUT_DIR']）")
    args = parser.parse_args()
    path = export_jiangya_channel_prices(args.brand, args.output_dir)
    print("[OK]", path)
