# jiangya_export_stockcount_to_excel.py
"""
导出鲸芽库存更新 Excel（固定 sheet/表头；分文件 490 行/文件）
- 函数签名保持不变：export_stock_excel(brand: str, output_dir: Optional[str] = None, filename: Optional[str] = None) -> str
- 仅导出 channel_product_id 非空（排除 NULL/空串）
- 字段：channel_product_id, skuid, stock_count
- sheet 名固定：sheet1
- 表头固定：['渠道产品ID(必填)', 'skuID', '库存(必填)']
- 分包：每个文件最多 490 条“数据行”（不含表头）

依赖：pandas openpyxl psycopg2-binary
"""

import re
from pathlib import Path
from typing import Optional, List, Set, Tuple

import pandas as pd
import openpyxl
import psycopg2

from config import BRAND_CONFIG
try:
    from config import PGSQL_CONFIG  # 兜底
except Exception:
    PGSQL_CONFIG = {}


_EMPTY_CELL = {"", "NAN", "NONE", "NAT"}
_SIZE_SPLIT_RE = re.compile(r"[,，、/;；\s]+")


def _norm_code(v) -> str:
    return str(v).strip().upper()


def _norm_size(v) -> str:
    """尺码归一化：去空格、大写，Excel 数字 43.0 → 43。"""
    s = str(v).strip().upper()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


def _load_exclude_from_excel(excel_path: Path) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    """
    从 Excel 读取库存导出排除名单。返回 (整款排除编码, {(编码, 尺码)} 按尺码排除)。

    - 编码列：列名含 'code' 或 '编码'（必需）
    - 尺码列：列名含 'size' 或 '尺码'（可选）
        * 尺码留空 → 该商品编码所有尺码都不导出（整款排除）
        * 尺码有值 → 只排除这些尺码，其余尺码正常导出；
          一格可填多个尺码，用逗号/顿号/斜杠/空格分隔，如 "42,43"
    文件不存在或无法解析时返回空集合。
    """
    if not excel_path.exists():
        print(f"[INFO] 排除名单文件未找到：{excel_path}（不做排除）")
        return set(), set()
    try:
        df_exc = pd.read_excel(excel_path, dtype=str)
    except Exception as e:
        print(f"[WARN] 无法读取排除名单Excel {excel_path}: {e}")
        return set(), set()

    code_cols = [c for c in df_exc.columns if "code" in str(c).lower() or "编码" in str(c)]
    if not code_cols:
        print(f"[WARN] 排除名单Excel中未找到含'code'/'编码'的列，列名={list(df_exc.columns)}")
        return set(), set()
    size_cols = [c for c in df_exc.columns if "size" in str(c).lower() or "尺码" in str(c)]
    code_col = code_cols[0]
    size_col = size_cols[0] if size_cols else None

    whole_codes: Set[str] = set()
    code_sizes: Set[Tuple[str, str]] = set()
    for _, row in df_exc.iterrows():
        code = _norm_code(row[code_col])
        if code in _EMPTY_CELL:
            continue
        raw_size = "" if size_col is None else str(row[size_col]).strip()
        if raw_size.upper() in _EMPTY_CELL:
            whole_codes.add(code)
            continue
        for s in _SIZE_SPLIT_RE.split(raw_size):
            s = _norm_size(s)
            if s and s not in _EMPTY_CELL:
                code_sizes.add((code, s))

    print(f"[INFO] 排除名单加载：整款 {len(whole_codes)} 个编码，按尺码 {len(code_sizes)} 个SKU"
          f"（编码列 '{code_col}'，尺码列 '{size_col or '无'}'）")
    return whole_codes, code_sizes


def _load_exclude_codes_from_excel(excel_path: Path) -> Set[str]:
    """兼容旧接口：只返回整款排除的商品编码。"""
    return _load_exclude_from_excel(excel_path)[0]

SHEET_NAME = "sheet1"
HEADERS = ["渠道产品ID(必填)", "skuID", "库存(必填)"]
CHUNK_SIZE = 490  # 每个文件最多的数据行数（不含表头）

def _write_one_excel(df_chunk: pd.DataFrame, file_path: Path):
    """按固定 sheet 与表头写一个 Excel（不依赖模板）"""
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

def export_stock_excel(
    brand: str,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
    exclude_excel_file: Optional[str] = None,
) -> str:
    """
    导出鲸芽库存更新 Excel。

    exclude_excel_file: 可选。排除名单 Excel 路径：
                        - 编码列（列名含 'code'/'编码'）必需
                        - 尺码列（列名含 'size'/'尺码'）可选；留空=整款排除，
                          有值=只排除该编码下的这些尺码（如自有 43 码库存，不随官网更新）
    """
    brand_l = brand.lower().strip()
    if brand_l not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}。可用：{', '.join(sorted(BRAND_CONFIG.keys()))}")

    cfg = BRAND_CONFIG[brand_l]
    table = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)
    if not pgcfg:
        raise RuntimeError("PGSQL 连接配置缺失，请在 config.py 中提供 PGSQL_CONFIG 或品牌级 PGSQL_CONFIG。")

    # 0) 加载白名单（若有）
    exclude_codes: Set[str] = set()
    exclude_code_sizes: Set[Tuple[str, str]] = set()
    if exclude_excel_file:
        exclude_codes, exclude_code_sizes = _load_exclude_from_excel(Path(exclude_excel_file))

    # 1) 读取数据：仅 channel_product_id 非空/非空串；同时取 product_code/size 供排除过滤
    conn = psycopg2.connect(
        host=pgcfg["host"], port=pgcfg["port"],
        user=pgcfg["user"], password=pgcfg["password"], dbname=pgcfg["dbname"],
    )
    sql = f"""
        SELECT channel_product_id, skuid, stock_count, product_code, size
        FROM {table}
        WHERE channel_product_id IS NOT NULL AND TRIM(channel_product_id) <> ''
    """
    df = pd.read_sql(sql, conn)
    conn.close()

    # 1b) 按排除名单过滤：整款 / 按尺码
    if exclude_codes or exclude_code_sizes:
        before = len(df)
        codes_n = df["product_code"].map(_norm_code)
        mask = codes_n.isin(exclude_codes)
        if exclude_code_sizes:
            sizes_n = df["size"].map(_norm_size)
            pair_hit = pd.Series(list(zip(codes_n, sizes_n)), index=df.index).isin(exclude_code_sizes)
            matched = set(zip(codes_n[pair_hit], sizes_n[pair_hit]))
            unmatched = exclude_code_sizes - matched
            if unmatched:
                print(f"[WARN] 以下 编码+尺码 在已绑定库存中未找到（请核对尺码写法）："
                      f"{sorted(unmatched)[:20]}{' ...' if len(unmatched) > 20 else ''}")
            mask |= pair_hit
        df = df[~mask]
        print(f"[INFO] 排除名单过滤：{before - len(df)} 条SKU（剩余 {len(df)} 条）")

    # 1c) 安全校验：已发布商品库存全零比例检查
    _ZERO_STOCK_ABORT_THRESHOLD = 0.70  # 超过70%的已发布商品库存全零时中止
    _MIN_PRODUCTS_FOR_CHECK = 10        # 商品数量太少时不做检查（避免误判新品牌）
    if not df.empty:
        df["stock_count"] = pd.to_numeric(df["stock_count"], errors="coerce").fillna(0)
        product_max_stock = df.groupby("product_code")["stock_count"].max()
        total_products = len(product_max_stock)
        zero_products = int((product_max_stock == 0).sum())
        zero_rate = zero_products / total_products if total_products > 0 else 0
        print(f"[CHECK] 已绑定商品 {total_products} 个 / 全尺码库存为0 {zero_products} 个 ({zero_rate:.0%})")
        if total_products >= _MIN_PRODUCTS_FOR_CHECK and zero_rate >= _ZERO_STOCK_ABORT_THRESHOLD:
            print(f"[🚨 中止] 库存全零商品占比 {zero_rate:.0%}，超过阈值 {_ZERO_STOCK_ABORT_THRESHOLD:.0%}，疑似数据异常")
            print(f"[🚨 中止] 已取消导出，请检查数据库库存数据后手动重新运行")
            return ""

    # 2) 清洗
    if df.empty:
        # 仍生成一个只有表头的空文件
        out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        base = Path(filename).stem if filename else f"{brand_l}_jiangya_stock_update"
        out_file = out_dir / f"{base}_part1_of1.xlsx"
        empty = pd.DataFrame(columns=HEADERS)
        _write_one_excel(empty, out_file)
        print(f"[INFO] 无可导出的记录，生成空表：{out_file}")
        return str(out_file)

    df["channel_product_id"] = df["channel_product_id"].astype(str).str.strip()
    df["skuid"] = df["skuid"].astype(str).fillna("0").replace({"": "0"})
    df["stock_count"] = pd.to_numeric(df["stock_count"], errors="coerce").fillna(0).astype(int)

    out_df = pd.DataFrame({
        "渠道产品ID(必填)": df["channel_product_id"],
        "skuID": df["skuid"],
        "库存(必填)": df["stock_count"],
    })[HEADERS]

    # 👉 在这里加排序
    out_df = out_df.sort_values(by=["渠道产品ID(必填)", "skuID"]).reset_index(drop=True)

    # 3) 分包写出：每文件最多 490 条数据行（不含表头）
    out_dir = Path(output_dir) if output_dir else Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)

    n = len(out_df)
    num_parts = (n + CHUNK_SIZE - 1) // CHUNK_SIZE if n > 0 else 1
    created_files: List[Path] = []

    # 输出文件名基底：如果调用者传了 filename 且只有 1 个分包，就用它；否则统一添加 part 序号
    base = Path(filename).stem if filename else f"{brand_l}_jiangya_stock_update"

    if n == 0:
        out_file = out_dir / f"{base}_part1_of1.xlsx"
        _write_one_excel(out_df, out_file)
        print(f"[INFO] 无有效记录，已生成空表：{out_file}")
        return str(out_file)

    for i in range(num_parts):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, n)
        df_chunk = out_df.iloc[start:end].reset_index(drop=True)

        if num_parts == 1 and filename:
            out_file = out_dir / (base + ".xlsx")
        else:
            out_file = out_dir / f"{base}_part{i+1}_of_{num_parts}.xlsx"

        _write_one_excel(df_chunk, out_file)
        created_files.append(out_file)
        print(f"[OK] 写出：{out_file}（行数：{len(df_chunk)}）")

    # 返回第一个文件路径，保持返回类型不变
    return str(created_files[0])


# CLI 入口：brand 必填；--output-dir/--filename 可选
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出鲸芽库存更新 Excel（固定 sheet/表头；分文件 490 行）")
    parser.add_argument("--brand", required=True, help="品牌名，例如 camper / clarks / geox / barbour")
    parser.add_argument("--output-dir", default=None, help="可选，指定导出目录（默认 BRAND_CONFIG[brand]['OUTPUT_DIR']）")
    parser.add_argument("--filename", default=None, help="可选，输出文件名基底；单文件时可用精准文件名")
    args = parser.parse_args()
    path = export_stock_excel(args.brand, args.output_dir, args.filename)
    print("[OK]", path)
