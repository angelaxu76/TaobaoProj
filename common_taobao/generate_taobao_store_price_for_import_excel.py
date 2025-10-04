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
    out_stock_qty: int = 0
):
    """
    批量处理 input_dir 下的所有 Excel，输出 SKU 级库存：
    - 如果 Excel 无“规格/尺码”列：按 product_code 归并，只要该款任一尺码有货→该款所有 skuID 统一写 in_stock_qty，否则 0。
    - 如果 Excel 有“sku规格/规格/尺码”列：按 (product_code, size) 精确匹配 DB 的 stock_status 输出库存。
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

    # 预取 DB 的库存明细：product_code,size,stock_status
    import pandas as _pd
    conn = psycopg2.connect(**pg)
    try:
        sql = f"SELECT product_code, size, stock_status FROM {table}"
        db_stock = _pd.read_sql(sql, conn)
    finally:
        conn.close()

    # 标准化
    db_stock["product_code"] = db_stock["product_code"].astype(str).str.strip()
    db_stock["size"] = db_stock["size"].astype(str).str.strip()
    db_stock["stock_status"] = db_stock["stock_status"].astype(str).str.strip()

    # 映射函数
    def status_to_qty(s: str) -> int:
        return in_stock_qty if str(s).strip() == "有货" else out_stock_qty

    results = []
    for f in files:
        try:
            out_name = f.stem + (suffix or "")
            if not out_name.endswith(".xlsx"):
                out_name += ".xlsx"
            out_path = output_dir / out_name
            print(f"▶️ {f.name} -> {out_name}")

            df0 = pd.read_excel(f, dtype=object)

            col_item = _normalize_col(df0, "item_id")
            col_code = _normalize_col(df0, "product_code")
            col_sku  = _normalize_col(df0, "skuid")

            # 额外尝试识别“规格/尺码”列（可选）
            spec_candidates = ["sku规格","规格","尺码","SKUspec","sku_spec","属性","销售属性"]
            col_spec = None
            canon2raw = {_canon(c): c for c in df0.columns}
            for cand in spec_candidates:
                if _canon(cand) in canon2raw:
                    col_spec = canon2raw[_canon(cand)]
                    break

            # 前向填充
            def _prep_ffill(col: str):
                s = df0[col].apply(lambda v: _to_text(v).strip())
                s = s.replace("", pd.NA)
                return s.ffill().fillna("")
            df0[col_item] = _prep_ffill(col_item)
            df0[col_code] = _prep_ffill(col_code)
            if col_spec:
                df0[col_spec] = _prep_ffill(col_spec)

            # 展开 SKU 行
            rows = []
            for _, r in df0.iterrows():
                item_id = _to_text(r.get(col_item)).strip()
                code    = _to_text(r.get(col_code)).strip()
                spec    = _to_text(r.get(col_spec)).strip() if col_spec else ""
                skus    = _split_skuids(r.get(col_sku))
                if not skus:
                    continue
                for sid in skus:
                    sid = _to_text(sid).strip()
                    if sid:
                        rows.append((item_id, code, spec, sid))
            if not rows:
                raise ValueError("输入Excel无有效记录（检查宝贝ID/商家编码/skuID列与内容）。")

            df_expanded = pd.DataFrame(rows, columns=["宝贝id","product_code","规格","skuid"])

            # 计算库存
            if col_spec:
                # 尝试从规格中抽取尺码（如果规格就是尺码，直接使用；如果格式是 “编码,尺码” 之类，可据你现状做解析）
                # 这里先直接拿整段规格与 DB 的 size 做“等值匹配”，必要时你可以加一个 normalize 映射
                df_tmp = df_expanded.merge(
                    db_stock.assign(调整后库存=db_stock["stock_status"].map(status_to_qty)),
                    left_on=["product_code","规格"], right_on=["product_code","size"], how="left"
                )
                df_tmp["调整后库存"] = df_tmp["调整后库存"].fillna(out_stock_qty).astype(int)
            else:
                # 无规格：按款聚合，只要该款有任何尺码“有货”→整款给 in_stock_qty，否则 0
                has_stock = (
                    db_stock.assign(qty=db_stock["stock_status"].map(status_to_qty))
                            .groupby("product_code")["qty"].max()
                            .reset_index()
                            .rename(columns={"qty":"调整后库存"})
                )
                df_tmp = df_expanded.merge(has_stock, on="product_code", how="left")
                df_tmp["调整后库存"] = df_tmp["调整后库存"].fillna(out_stock_qty).astype(int)

            # 导出两列（若要带宝贝id就把列换成 ["宝贝id","skuid","调整后库存"]）
            df_out = df_tmp[["skuid","调整后库存"]]
            df_out.to_excel(out_path, index=False)
            print(f"✅ 已导出：{out_path} | 输出SKU行数: {len(df_out)}")
            results.append((str(f), str(out_path), None))
        except Exception as e:
            print(f"❌ 处理失败：{f} | 错误：{e}")
            results.append((str(f), None, str(e)))
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
