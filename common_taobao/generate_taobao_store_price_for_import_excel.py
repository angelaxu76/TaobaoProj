# -*- coding: utf-8 -*-
"""
逐 SKU 导出店铺价格（修正版）
- 从 input_dir 自动选择最近修改的 Excel（随机文件名）
- 识别列：宝贝ID(=item_id)、商家编码(=product_code)、skuID(=skuid)
- 对于一行中多个 skuID（逗号/分号/空格/换行等）会展开为多行
- 到品牌表查询 taobao_store_price，查不到则跳过（非鲸芽模式）
- 输出三列：宝贝id | skuid | 调整后价格
"""
from pathlib import Path
import unicodedata
import re
from typing import List, Dict, Optional, Iterable
import pandas as pd
import psycopg2
from config import BRAND_CONFIG

# ===== 列名别名：精确贴合你系统导出的表头 =====
COL_ALIASES = {
    "item_id": {"item_id","itemid","ITEM_ID","宝贝id","宝贝ID","宝贝Id","宝贝"},
    "product_code": {
        "product_code","productcode","code",
        "商品编码","商品Code","产品编码","编码","货号",
        "商家编码",              # ✅ 你表头里的列
        "商家货号","外部编码","外部代码",
        "outer_id","outerid","outer code","outercode"
    },
    "skuid": {
        "skuid","sku_id","SkuId","SKU_ID","SKUID",
        "skuID",                 # ✅ 你表头里的列
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

def _find_latest_excel(input_dir: Path) -> Path:
    files = list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls"))
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]

def _split_skuids(val) -> List[str]:
    if pd.isna(val): return []
    # 避免科学计数
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        val = str(int(val))
    s = str(val).strip()
    if not s: return []
    parts = [p.strip() for p in _SPLIT.split(s) if p.strip()]
    # 清洗：移除非字母数字和下划线/短横线以外字符
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
    missing = list(dict.fromkeys(codes))  # 去重但保持顺序

    # 优先 product_code
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
            # 表可能没有 product_code 列，忽略进入兜底
            pass

        # 兜底：某些历史表把编码放 product_name
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

import math
import pandas as pd

def _to_text(v: object) -> str:
    """把任意Excel单元格安全转成字符串：空->''；数值->不带科学计数；其余->str()."""
    if v is None or (isinstance(v, float) and (math.isnan(v))):
        return ""
    # pandas 会把整数型/长数字读成 float；这里确保不输出科学计数
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        # 如果是整数值的 float（如 1.0），转成整数字符串
        if v.is_integer():
            return str(int(v))
        # 非整数：去掉科学计数，最多保留15位有效数字
        return f"{v:.15g}"
    # pandas 的 NA/NaT 之类
    if isinstance(v, pd._libs.missing.NAType) or (isinstance(v, str) and v.lower() == "nan"):
        return ""
    return str(v)


# 严格不丢SKU版本：以 skuID 为主键输出
def generate_price_excel(
    brand: str,
    input_dir: str | Path,
    output_path: str | Path,
    drop_rows_without_price: bool = True  # 按你要求：编码不在库里 => 整行跳过
) -> Path:
    """
    以 skuID 为主输出：每个 skuID 一行，且“宝贝id、价格”都填上。
    做法：
      1) 读取目录中最近的 Excel（系统导出表头：宝贝ID/商家编码/skuID）
      2) 对【宝贝ID、商家编码】做向下填充（ffill），解决后续行留空问题
      3) 逐行（或按单元格内多个sku拆分）产出 (item_id, product_code, skuid)
      4) 按 product_code 查库得 taobao_store_price，并左连接
      5) 默认丢弃无价行（编码不在库里），保留的每行都填好 宝贝id & 价格
      6) 输出三列：宝贝id | skuid | 调整后价格
    """
    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")

    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir = Path(input_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) 读入原表（保留原始类型，后面统一转文本）
    excel_file = _find_latest_excel(input_dir)
    print(f"📄 使用输入文件：{excel_file}")
    df0 = pd.read_excel(excel_file, dtype=object)

    # 2) 列名定位
    col_item = _normalize_col(df0, "item_id")       # 宝贝ID
    col_code = _normalize_col(df0, "product_code")  # 商家编码
    col_sku  = _normalize_col(df0, "skuid")         # skuID

    # 2.1) 向下填充宝贝ID/商家编码 —— 关键修复点
    def _prep_ffill(col: str):
        s = df0[col].apply(lambda v: _to_text(v).strip())
        s = s.replace("", pd.NA)
        return s.ffill().fillna("")  # 顶部若为空仍给空串

    df0[col_item] = _prep_ffill(col_item)
    df0[col_code] = _prep_ffill(col_code)

    # 3) 逐行产出（支持一格多个sku的情况）
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

    # 4) 查价并左连接（不丢SKU）
    codes = list(dict.fromkeys(df_expanded["product_code"].tolist()))
    conn = psycopg2.connect(**pg)
    try:
        price_map = _fetch_prices(conn, table, codes)  # {code: price 或 None}
    finally:
        conn.close()

    df_price = pd.DataFrame(
        [{"product_code": k, "调整后价格": v} for k, v in price_map.items()],
        columns=["product_code", "调整后价格"]
    )
    df_merged = df_expanded.merge(df_price, on="product_code", how="left")

    # 5) 丢弃无价（编码不在库）或保留空价 —— 默认按你要求丢弃
    if drop_rows_without_price:
        before = len(df_merged)
        df_out = df_merged[df_merged["调整后价格"].notna()].copy()
        print(f"🧹 跳过(无价/非鲸芽)SKU行: {before - len(df_out)}")
    else:
        df_out = df_merged.copy()
        df_out.loc[df_out["调整后价格"].isna(), "调整后价格"] = ""

    # 6) 只导出三列；每个 skuID 一行，且“宝贝id / 价格”已填好
    df_out = df_out[["宝贝id", "skuid", "调整后价格"]]
    df_out.to_excel(output_path, index=False)
    print(f"✅ 已导出：{output_path} | 输出SKU行数: {len(df_out)} | 宝贝数: {df_out['宝贝id'].nunique()}")
    return output_path





if __name__ == "__main__":
    # 简单命令行：python generate_taobao_store_price_for_import_excel.py camper D:\in D:\out\camper_prices.xlsx
    import sys, traceback
    if len(sys.argv) >= 4:
        try:
            generate_price_excel(sys.argv[1], sys.argv[2], sys.argv[3])
        except Exception as e:
            print("❌ 失败：", e); traceback.print_exc()
    else:
        print("用法: python this_script.py <brand> <input_dir> <output_excel_path>")
