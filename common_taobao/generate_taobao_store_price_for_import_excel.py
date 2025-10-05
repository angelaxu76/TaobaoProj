# -*- coding: utf-8 -*-
"""
逐 SKU 导出店铺价格（支持批量）
- 单文件：保持 generate_price_excel(brand, input_dir, output_path) 原行为不变（取 input_dir 内“最近修改”的一个Excel）
- 批量：新增 generate_price_excels_bulk(brand, input_dir, output_dir, suffix)
  * 处理 input_dir 下所有 *.xlsx / *.xls
  * 输出文件名 = 输入文件名（不含扩展名） + suffix + ".xlsx"
  * 每个文件独立查价、独立导出，单个失败不影响其它文件
- 列识别：宝贝ID(=item_id)、商家编码(=product_code)、skuID(=skuid)
- 价格来源：品牌表中的 taobao_store_price（优先 product_code；兜底 product_name）
- 输出三列：宝贝id | skuid | 调整后价格
"""
from pathlib import Path
import unicodedata
import re
from typing import List, Dict, Optional, Iterable, Tuple
import pandas as pd
import psycopg2
import math

from config import BRAND_CONFIG

# ===== 列名别名 =====
COL_ALIASES = {
    "item_id": {"item_id","itemid","ITEM_ID","宝贝id","宝贝ID","宝贝Id","宝贝"},
    "product_code": {
        "product_code","productcode","code",
        "商品编码","商品Code","产品编码","编码","货号",
        "商家编码",
        "商家货号","外部编码","外部代码",
        "outer_id","outerid","outer code","outercode"
    },
    "skuid": {
        "skuid","sku_id","SkuId","SKU_ID","SKUID",
        "skuID",
        "渠道货品ID","渠道skuid","货品id","货品ID"
    },
}

_SPLIT = re.compile(r"[,\uFF0C;；\s\r\n]+")



def _canon(s: str) -> str:
    if s is None: return ""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = s.replace("\u00A0", " ").replace("\u200B", "")
    return s.lower()

def _normalize_col(df: pd.DataFrame, want: str) -> str:
    canon2raw = {_canon(c): c for c in df.columns}
    for alias in COL_ALIASES[want]:
        key = _canon(alias)
        if key in canon2raw:
            return canon2raw[key]
    raise KeyError(f"Excel中缺少必要列：{want}（可用别名：{COL_ALIASES[want]}），当前表头：{list(df.columns)}")

def _list_excels(input_dir: Path) -> List[Path]:
    files = list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

def _find_latest_excel(input_dir: Path) -> Path:
    files = _list_excels(input_dir)
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")
    return files[0]

def _split_skuids(val) -> List[str]:
    if pd.isna(val): return []
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        val = str(int(val))
    s = str(val).strip()
    if not s: return []
    parts = [p.strip() for p in _SPLIT.split(s) if p.strip()]
    parts = [re.sub(r"[^\w\-]", "", p) for p in parts if p]
    return [p for p in parts if p]

def _chunked(it: Iterable, size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf; buf = []
    if buf: yield buf

def _fetch_prices(conn, table: str, codes: List[str]) -> Dict[str, Optional[float]]:
    prices: Dict[str, Optional[float]] = {}
    missing = list(dict.fromkeys(codes))
    with conn.cursor() as cur:
        try:
            for chunk in _chunked(missing, 1000):
                cur.execute(
                    f"SELECT product_code, taobao_store_price FROM {table} "
                    f"WHERE product_code = ANY(%s)", (chunk,))
                for code, price in cur.fetchall():
                    prices[str(code)] = None if price is None else float(price)
            missing = [c for c in missing if c not in prices]
        except Exception:
            pass
        if missing:
            try:
                for chunk in _chunked(missing, 1000):
                    cur.execute(
                        f"SELECT product_name, taobao_store_price FROM {table} "
                        f"WHERE product_name = ANY(%s)", (chunk,))
                    for code, price in cur.fetchall():
                        prices[str(code)] = None if price is None else float(price)
            except Exception:
                pass
    return prices

def _to_text(v: object) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v))):
        return ""
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.15g}"
    if isinstance(v, pd._libs.missing.NAType) or (isinstance(v, str) and v.lower() == "nan"):
        return ""
    return str(v)

# ===== 单文件：保持兼容 =====
def generate_price_excel(
    brand: str,
    input_dir: str | Path,
    output_path: str | Path,
    drop_rows_without_price: bool = True
) -> Path:
    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")
    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir = Path(input_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    excel_file = _find_latest_excel(input_dir)
    print(f"📄 使用输入文件：{excel_file}")
    return _generate_price_excel_from_file(brand, excel_file, output_path, drop_rows_without_price, table, pg)

# ===== 批量：处理 input_dir 下所有 Excel =====
def generate_price_excels_bulk(
    brand: str,
    input_dir: str | Path,
    output_dir: str | Path,
    suffix: str = "_价格",
    drop_rows_without_price: bool = True
):
    """
    批量处理 input_dir 下的所有 Excel；输出文件名 = 输入文件名(不含扩展名) + suffix + ".xlsx"
    """
    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")
    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = _list_excels(input_dir)
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")

    results = []
    for f in files:
        try:
            out_name = f.stem + (suffix or "")
            if not out_name.endswith(".xlsx"):
                out_name += ".xlsx"
            out_path = output_dir / out_name
            print(f"▶️ {f.name} -> {out_name}")
            _generate_price_excel_from_file(brand, f, out_path, drop_rows_without_price, table, pg)
            results.append((str(f), str(out_path), None))
        except Exception as e:
            print(f"❌ 处理失败：{f} | 错误：{e}")
            results.append((str(f), None, str(e)))
    return results

def _generate_price_excel_from_file(
    brand: str,
    excel_file: Path,
    output_path: Path,
    drop_rows_without_price: bool,
    table: str,
    pg: dict
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"📄 处理：{excel_file}")
    df0 = pd.read_excel(excel_file, dtype=object)

    col_item = _normalize_col(df0, "item_id")
    col_code = _normalize_col(df0, "product_code")
    col_sku  = _normalize_col(df0, "skuid")

    def _prep_ffill(col: str):
        s = df0[col].apply(lambda v: _to_text(v).strip())
        s = s.replace("", pd.NA)
        return s.ffill().fillna("")

    df0[col_item] = _prep_ffill(col_item)
    df0[col_code] = _prep_ffill(col_code)

    rows = []
    for _, r in df0.iterrows():
        item_id = _to_text(r.get(col_item)).strip()
        code    = _to_text(r.get(col_code)).strip()
        skus    = _split_skuids(r.get(col_sku))
        if not skus:
            continue
        for sid in skus:
            sid = _to_text(sid).strip()
            if sid:
                rows.append((item_id, code, sid))

    if not rows:
        raise ValueError("输入Excel无有效记录（检查宝贝ID/商家编码/skuID列与内容）。")

    df_expanded = pd.DataFrame(rows, columns=["宝贝id", "product_code", "skuid"])
    print(f"🔎 展开后SKU行数: {len(df_expanded)} | 宝贝数: {df_expanded['宝贝id'].nunique()} | 唯一SKU数: {df_expanded['skuid'].nunique()}")

    conn = psycopg2.connect(**pg)
    try:
        codes = list(dict.fromkeys(df_expanded["product_code"].tolist()))
        price_map = _fetch_prices(conn, table, codes)
    finally:
        conn.close()

    df_price = pd.DataFrame(
        [{"product_code": k, "调整后价格": v} for k, v in price_map.items()],
        columns=["product_code", "调整后价格"]
    )
    df_merged = df_expanded.merge(df_price, on="product_code", how="left")

    if drop_rows_without_price:
        before = len(df_merged)
        df_out = df_merged[df_merged["调整后价格"].notna()].copy()
        print(f"🧹 跳过(无价/非鲸芽)SKU行: {before - len(df_out)}")
    else:
        df_out = df_merged.copy()
        df_out.loc[df_out["调整后价格"].isna(), "调整后价格"] = ""

    df_out = df_out[["宝贝id", "skuid", "调整后价格"]]
    df_out.to_excel(output_path, index=False)
    print(f"✅ 已导出：{output_path} | 输出SKU行数: {len(df_out)} | 宝贝数: {df_out['宝贝id'].nunique()}")
    return output_path


# ===== 新增：批量导出 SKU 库存 =====
def generate_stock_excels_bulk(
    brand: str,
    input_dir: str | Path,
    output_dir: str | Path,
    suffix: str = "_库存",
    in_stock_qty: int = 3,
    out_stock_qty: int = 0,
):
    """
    批量根据 input_dir 下的店铺导出表生成“SKUID | 调整后库存”的 Excel。
    规则与 generate_price_excels_bulk 保持一致：仅按 product_code 合并，全款同值。
    - 数据来源：<TABLE_NAME> 中的 taobao_store_price 字段：
        * '有货'  -> in_stock_qty（默认3）
        * 其他/空 -> out_stock_qty（默认0）
    - 输出：<输入文件名+suffix>.xlsx，只有两列：SKUID, 调整后库存
    """
    import pandas as pd
    import psycopg2
    from pathlib import Path

    def _to_text(v):
        if v is None:
            return ""
        s = str(v).strip()
        return s

    def _list_excels(input_dir: Path):
        return (list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls")))

    def status_to_qty_from_price(val: str) -> int:
        # 按你要求：如果 taobao_store_price 字段文本为“有货” => 3，否则 => 0
        #（注意：如果该字段在某些品牌是“数字价格”，此映射会失真，需要改回 stock_status）
        s = _to_text(val)
        return in_stock_qty if s == "有货" else out_stock_qty

    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")
    cfg   = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir  = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 拉取“可售状态”并做映射（仅按 product_code）
    conn = psycopg2.connect(**pg)
    try:
        df_flag = pd.read_sql(f'SELECT product_code, taobao_store_price FROM {table}', conn)
    finally:
        conn.close()

    if "product_code" not in df_flag.columns:
        raise RuntimeError(f"{table} 缺少 product_code 列")

    df_flag["product_code"] = df_flag["product_code"].astype(str).str.strip()
    # 统一映射为数量
    df_flag["调整后库存"] = df_flag["taobao_store_price"].map(status_to_qty_from_price)
    # 按款聚合（若同一款多行，取最大——等价“只要有一行有货则有货”）
    qty_by_code = (
        df_flag.groupby("product_code")["调整后库存"].max()
               .reset_index()
    )

    # 2) 扫描输入目录
    files = _list_excels(input_dir)
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")

    results = []
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            df0 = pd.read_excel(f, dtype=object)

            # 复用你现有的列名别名解析
            col_item = _normalize_col(df0, "item_id")        # 宝贝id
            col_code = _normalize_col(df0, "product_code")   # 商家编码
            col_sku  = _normalize_col(df0, "skuid")          # skuID

            # 展开 SKU 行（与价格导出一致：只按 product_code 合并，不看尺码）
            rows = []
            for _, r in df0.iterrows():
                item_id = _to_text(r.get(col_item))
                code    = _to_text(r.get(col_code))
                skus    = _split_skuids(r.get(col_sku))
                for sid in skus:
                    sid = _to_text(sid)
                    if sid:
                        rows.append((item_id, code, sid))

            if not rows:
                raise ValueError(f"{f.name} 无有效 SKU 记录（检查宝贝ID/商家编码/skuID）。")

            df_expanded = pd.DataFrame(rows, columns=["宝贝id", "product_code", "skuid"])
            df_expanded["product_code"] = df_expanded["product_code"].astype(str).str.strip()

            # 仅按 product_code 合并库存数量（与价格导出相同合并粒度）
            df_tmp = df_expanded.merge(qty_by_code, on="product_code", how="left")
            df_tmp["调整后库存"] = df_tmp["调整后库存"].fillna(out_stock_qty).astype(int)

            # 输出两列
            out_df = df_tmp[["skuid", "调整后库存"]]
            out_name = f.stem + (suffix or "")
            if not out_name.endswith(".xlsx"):
                out_name += ".xlsx"
            out_path = output_dir / out_name
            out_df.to_excel(out_path, index=False)

            print(f"✅ {f.name} -> {out_name} (rows={len(out_df)})")
            results.append((str(f), str(out_path), len(out_df), None))
        except Exception as e:
            print(f"❌ 处理失败：{f} | 错误：{e}")
            results.append((str(f), None, 0, str(e)))

    return results



if __name__ == "__main__":
    # 用法一：单文件（保持兼容）
    #   python this_script.py <brand> <input_dir> <output_excel_path>
    # 用法二：批量（推荐你现在的场景）
    #   python this_script.py <brand> <input_dir> <output_dir> --bulk [--suffix "_价格"]
    import sys, traceback
    try:
        if len(sys.argv) >= 5 and sys.argv[4] == "--bulk":
            brand = sys.argv[1]
            input_dir = sys.argv[2]
            output_dir = sys.argv[3]
            suffix = "_价格"
            if len(sys.argv) >= 7 and sys.argv[5] == "--suffix":
                suffix = sys.argv[6]
            results = generate_price_excels_bulk(brand, input_dir, output_dir, suffix=suffix, drop_rows_without_price=True)
            ok = [r for r in results if r[1] is not None]
            bad = [r for r in results if r[1] is None]
            print(f"📦 批量完成：成功 {len(ok)} 个，失败 {len(bad)} 个")
            if bad:
                print("失败清单：")
                for f, _, err in bad:
                    print(f" - {f} -> 错误：{err}")
        elif len(sys.argv) >= 4:
            generate_price_excel(sys.argv[1], sys.argv[2], sys.argv[3])
        else:
            print("用法：")
            print("  单文件：python this_script.py <brand> <input_dir> <output_excel_path>")
            print('  批  量：python this_script.py <brand> <input_dir> <output_dir> --bulk [--suffix "_价格"]')
    except Exception as e:
        print("❌ 失败：", e)
        traceback.print_exc()
