from pathlib import Path
from typing import Dict, List, Optional, Set, Iterable, Tuple

import pandas as pd
import psycopg2
from psycopg2 import sql

from config import PGSQL_CONFIG, BRAND_CONFIG


def _connect():
    return psycopg2.connect(
        host=PGSQL_CONFIG["host"],
        port=PGSQL_CONFIG["port"],
        user=PGSQL_CONFIG["user"],
        password=PGSQL_CONFIG["password"],
        dbname=PGSQL_CONFIG["dbname"],
    )


import re

def _norm_code(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()

    # 处理类似 "18648.0"
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]

    # 去掉多余空格并统一大写
    return s.upper()



def _detect_stock_filter(cur, table_name: str) -> Optional[str]:
    """兼容 stock_count / stock_status（按你的项目现状）"""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    cols = {r[0].lower() for r in cur.fetchall()}
    if "stock_count" in cols:
        return "stock_count > 0"
    if "stock_status" in cols:
        return "stock_status = '有货'"
    return None


def _get_discount_codes_from_db(
    brand: str,
    min_discount_percent: float,
    only_in_stock: bool = False,
    limit: Optional[int] = None,
) -> List[str]:
    """
    折扣率定义： (1 - discount_price/original_price)*100
    条件：折扣率 >= X%  <=>  discount/original <= 1 - X%
    """
    brand = (brand or "").strip().lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌: {brand}. 可选: {list(BRAND_CONFIG.keys())}")

    cfg = BRAND_CONFIG[brand]  # 来自 config.py :contentReference[oaicite:2]{index=2}
    table_name = str(cfg["TABLE_NAME"]).strip().lower()
    fields = cfg.get("FIELDS", {})

    col_code = fields.get("product_code", "product_code")
    col_original = fields.get("original_price", "original_price_gbp")
    col_discount = fields.get("discount_price", "discount_price_gbp")

    min_ratio = 1.0 - (float(min_discount_percent) / 100.0)

    conn = _connect()
    try:
        with conn, conn.cursor() as cur:
            stock_sql = _detect_stock_filter(cur, table_name) if only_in_stock else None

            where_parts = [
                sql.SQL("{o} IS NOT NULL").format(o=sql.Identifier(col_original)),
                sql.SQL("{d} IS NOT NULL").format(d=sql.Identifier(col_discount)),
                sql.SQL("{o} > 0").format(o=sql.Identifier(col_original)),
                sql.SQL("{d} > 0").format(d=sql.Identifier(col_discount)),
                sql.SQL("({d}/{o}) <= %s").format(
                    d=sql.Identifier(col_discount),
                    o=sql.Identifier(col_original),
                ),
            ]
            params = [min_ratio]

            if stock_sql:
                where_parts.append(sql.SQL(stock_sql))

            q = sql.SQL("""
                SELECT DISTINCT {code}
                FROM {table}
                WHERE {where}
                ORDER BY {code}
            """).format(
                code=sql.Identifier(col_code),
                table=sql.Identifier(table_name),
                where=sql.SQL(" AND ").join(where_parts),
            )

            if limit is not None:
                q += sql.SQL(" LIMIT %s")
                params.append(int(limit))

            cur.execute(q, params)
            return [r[0] for r in cur.fetchall() if r and r[0]]
    finally:
        conn.close()


def _extract_codes_from_store_excels(store_dir: Path) -> Set[str]:
    """
    读取某个店铺目录下所有 excel，提取“商家编码/商品编码”集合
    """
    codes: Set[str] = set()
    excels = list(store_dir.glob("*.xls*"))
    if not excels:
        return codes

    for f in excels:
        try:
            df = pd.read_excel(f)
        except Exception as e:
            print(f"[WARN] 读取失败: {f} -> {e}")
            continue

        code_col = None
        for c in df.columns:
            if str(c).strip() in ("商家编码", "商品编码"):
                code_col = c
                break

        if code_col is None:
            print(f"[WARN] 跳过(未找到编码列): {f.name}, columns={list(df.columns)}")
            continue

        for v in df[code_col].dropna().tolist():
            code = _norm_code(v)
            if code:
                codes.add(code)

    return codes


def _write_codes_txt(codes: Iterable[str], txt_path: Path) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(",".join(list(codes)), encoding="utf-8")


def _safe_store_name_from_filename(p: Path) -> str:
    # 例如：五小剑camper.xlsx -> 五小剑camper
    return p.stem.strip()


def _extract_itemids_from_one_store_excel(excel_path: Path) -> Dict[str, str]:
    """
    从单个店铺Excel构建：商家编码 -> 宝贝ID
    关键：dtype=str 避免 18648.0 / 科学计数法 导致匹配失败
    """
    df = pd.read_excel(excel_path, dtype=str)  # ✅ 关键

    code_col = None
    id_col = None
    for c in df.columns:
        name = str(c).strip()
        if name in ("商家编码", "商品编码"):
            code_col = c
        if name in ("宝贝ID", "宝贝id", "商品ID", "item_id", "ItemID"):
            id_col = c

    if code_col is None or id_col is None:
        raise ValueError(f"Excel缺少必要列(商家编码/宝贝ID): {excel_path.name}, columns={list(df.columns)}")

    mapping: Dict[str, str] = {}
    sub = df[[code_col, id_col]].dropna()

    for _, row in sub.iterrows():
        code = _norm_code(row[code_col])
        if not code:
            continue

        item_id = str(row[id_col]).strip()
        # item_id 也可能出现 "12345.0"
        if item_id.endswith(".0") and item_id.replace(".0", "").isdigit():
            item_id = item_id[:-2]

        if code not in mapping and item_id:
            mapping[code] = item_id

    return mapping



def export_discount_itemids_to_ztc_txts(
    brand: str,
    min_discount_percent: float,
    taobao_store_excels_dir: str,
    output_txt_dir: str,
    only_in_stock: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Dict[str, int]]:
    """
    ✅ 你最终要的版本：
    输入：
      1) brand
      2) 折扣阈值（例如 39 表示“减39%以上”）
      3) taobao_store_excels_dir：一个目录，里面放多个店铺导出的 Excel（每个Excel=一个店铺）
      4) output_txt_dir：输出目录

    输出：
      每个店铺一个 txt：内容=宝贝ID，用英文逗号分隔，可直接粘贴直通车
    """
    store_dir = Path(taobao_store_excels_dir)
    if not store_dir.exists():
        raise FileNotFoundError(f"店铺Excel目录不存在: {store_dir}")

    out_dir = Path(output_txt_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step1: DB候选编码
    candidate_codes = [_norm_code(c) for c in _get_discount_codes_from_db(
        brand=brand,
        min_discount_percent=min_discount_percent,
        only_in_stock=only_in_stock,
        limit=limit,
    )]
    candidate_set = set(candidate_codes)

    # Step2: 遍历每个店铺Excel（一个Excel代表一个店铺）
    excel_files = sorted(list(store_dir.glob("*.xls*")))
    if not excel_files:
        raise FileNotFoundError(f"目录下未找到Excel: {store_dir}")

    stats: Dict[str, Dict[str, int]] = {}

    for excel_path in excel_files:
        store_name = _safe_store_name_from_filename(excel_path)
        code_to_itemid = _extract_itemids_from_one_store_excel(excel_path)

        # 候选编码在该店铺存在的 → 转成item_id（去重，保持候选顺序）
        seen = set()
        item_ids: List[str] = []
        matched_codes = 0

        for code in candidate_codes:
            item_id = code_to_itemid.get(code)
            if not item_id:
                continue
            matched_codes += 1
            if item_id not in seen:
                seen.add(item_id)
                item_ids.append(item_id)

        txt_path = out_dir / f"ztc_itemids_{brand}_{min_discount_percent}_{store_name}.txt"
        txt_path.write_text(",".join(item_ids), encoding="utf-8")

        print(f"[OK] {store_name}: matched_codes={matched_codes}, item_ids={len(item_ids)} -> {txt_path}")

        stats[store_name] = {
            "db_candidates": len(candidate_set),
            "store_rows_mapped": len(code_to_itemid),
            "matched_codes": matched_codes,
            "exported_item_ids": len(item_ids),
        }

        print("[DEBUG] sample candidate:", candidate_codes[:10])
        print("[DEBUG] sample excel codes:", list(code_to_itemid.keys())[:10])
        print("[DEBUG] hit sample:", [c for c in candidate_codes[:50] if c in code_to_itemid][:10])


    return stats



# 示例
if __name__ == "__main__":
    export_discount_codes_to_ztc_txts(
        brand="camper",
        min_discount_percent=39,
        taobao_stores_root_dir=r"D:\TB\Products\camper\document\store_prices",
        output_txt_dir=r"D:\TB\Products\camper\document\ztc_txt_out",
        only_in_stock=True,
    )
