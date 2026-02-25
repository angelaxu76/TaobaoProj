from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG


CATALOG_TABLE = "catalog_items"

# ========= Excel 列名候选映射 =========
# 你导出的字段：宝贝id / 宝贝标题 / 一口价 / 发布时间 / 商家编码 / 品牌
COLUMN_CANDIDATES: Dict[str, List[str]] = {
    "current_item_id": ["宝贝id", "宝贝ID", "item_id", "Item ID", "商品ID", "商品id", "宝贝Id"],
    "product_code": ["商家编码", "商品编码", "货号", "product_code", "编码", "Product Code"],
    "item_name": ["宝贝标题", "商品名称", "宝贝名称", "商品标题", "title", "名称", "Item Name"],
    "brand": ["品牌", "brand", "Brand"],
    "category": ["类目", "category", "Category"],
    "list_price": ["一口价", "标价", "list_price", "价格", "List Price"],
    # ✅ 新增：把“发布时间”写入业务字段 publication_date
    "publication_date": ["发布时间", "发布日", "上架时间", "首次发布时间", "发布时间(UTC)"],
}

# ========= DB 字段（我们会写入/更新的列）=========
WRITE_COLS = ["product_code", "item_name", "brand", "category", "list_price", "current_item_id", "publication_date"]
UPDATE_COLS = ["product_code", "item_name", "brand", "category", "list_price", "publication_date"]  # update 时不改 current_item_id


# ========= Brand 规范化（入库统一为英文 key） =========
BRAND_KEY_MAP = {
    "clarks": "clarks",
    "camper": "camper",
    "ecco": "ecco",
    "geox": "geox",
    "barbour": "barbour",
}

def normalize_brand(raw: Any) -> Optional[str]:
    s = _to_str(raw)
    if not s:
        return None
    # 1) 去空格 + 小写
    s = s.strip()
    # 2) 有 / 的取左边（如 "Ecco/爱步" -> "Ecco"）
    s = s.split("/", 1)[0].strip()
    s = s.lower()

    # 3) 同义词兜底（可按你数据再加）
    # 例如有人写成 "geox " / "GEOX鞋" 之类，可在这里扩展规则
    return BRAND_KEY_MAP.get(s, s)  # 未知就返回清洗后的原值


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except Exception:
        pass
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _to_str(v: Any) -> Optional[str]:
    if _is_empty(v):
        return None
    s = str(v).strip()
    return s if s else None


def _to_int(v: Any) -> Optional[int]:
    if _is_empty(v):
        return None
    try:
        return int(float(str(v).strip()))
    except Exception:
        return None


def _to_price(v: Any) -> Optional[float]:
    """
    支持：2210 / '2,210' / '£2,210.00' 等
    """
    if _is_empty(v):
        return None
    s = str(v).strip().replace(",", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_date(v: Any) -> Optional[date]:
    """
    Excel 里的“发布时间”写入 publication_date (date)
    """
    if _is_empty(v):
        return None
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _pick_excel_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    返回：规范字段 -> Excel 实际列名
    """
    mapping: Dict[str, str] = {}
    cols = list(df.columns)

    for canonical, candidates in COLUMN_CANDIDATES.items():
        for c in candidates:
            if c in cols:
                mapping[canonical] = c
                break

    # 强制要求：至少要有 current_item_id（用于关联 & 去重）
    if "current_item_id" not in mapping:
        raise ValueError(f"Excel 缺少宝贝ID列。候选：{COLUMN_CANDIDATES['current_item_id']}")

    return mapping


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "current_item_id": _to_int(row.get("current_item_id")),
        "product_code": _to_str(row.get("product_code")),
        "item_name": _to_str(row.get("item_name")),
        "brand": normalize_brand(row.get("brand")),
        "category": _to_str(row.get("category")),
        "list_price": _to_price(row.get("list_price")),
        "publication_date": _to_date(row.get("publication_date")),
    }


def ensure_publication_date_column(conn) -> None:
    """
    ✅ 如果你还没加 publication_date，这里会自动加（不改原结构逻辑，只做增量字段）
    如果你已加，这段不会有任何影响。
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name='publication_date'
        """, (CATALOG_TABLE,))
        exists = cur.fetchone() is not None

        if not exists:
            cur.execute(f"ALTER TABLE {CATALOG_TABLE} ADD COLUMN publication_date date;")
            conn.commit()
            print("✅ 已自动为 catalog_items 添加 publication_date(date) 字段")


def ensure_indexes(conn) -> None:
    """
    只建“不会限制业务”的普通索引（不对 product_code 做 unique）
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_items_product_code
            ON catalog_items (product_code)
            WHERE product_code IS NOT NULL;
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_items_current_item_id
            ON catalog_items (current_item_id)
            WHERE current_item_id IS NOT NULL;
        """)
    conn.commit()


def load_existing_by_item_id(conn, item_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    从 DB 读取已有记录：current_item_id -> row
    """
    if not item_ids:
        return {}

    sql = f"""
    SELECT id, current_item_id, product_code, item_name, brand, category, list_price, publication_date
    FROM {CATALOG_TABLE}
    WHERE current_item_id = ANY(%s)
    """
    df = pd.read_sql(sql, conn, params=(item_ids,))
    existing: Dict[int, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        cid = int(r["current_item_id"])
        existing[cid] = r.to_dict()
    return existing


def diff_fields(new_row: Dict[str, Any], old_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    返回需要更新的字段（只更新 UPDATE_COLS）
    规则：Excel 有值就优先；Excel 空则不覆盖 DB（避免把老数据清空）
    """
    changed: Dict[str, Any] = {}
    for k in UPDATE_COLS:
        nv = new_row.get(k)
        ov = old_row.get(k)

        # Excel 空值：不覆盖
        if nv is None:
            continue

        # list_price 浮点比较
        if k == "list_price":
            if ov is None or abs(float(nv) - float(ov)) > 1e-9:
                changed[k] = nv
            continue

        # 日期/字符串正常比较
        if nv != ov:
            changed[k] = nv

    return changed


def import_catalog_items_from_excel(
    excel_path: str,
    sheet_name: str | int | None = 0,
    create_unique_index: bool = True,
    **kwargs
):

    """
    ✅ 外部调用入口：
        import_catalog_items_from_excel(r"D:\\TB\\Reports\\商品统计_20251230.xlsx")
    """
    df = pd.read_excel(excel_path, sheet_name=sheet_name)

    if isinstance(df, dict):
        if not df:
            raise ValueError("Excel 未读取到任何 sheet")
        # 默认取第一个 sheet（与 Excel UI 行为一致）
        df = next(iter(df.values()))


    df = df.where(pd.notna(df), None)

    col_map = _pick_excel_columns(df)

    # 提取并规范化数据
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        raw = {k: r[col] if col in df.columns else None for k, col in col_map.items()}
        nr = _normalize_row(raw)
        if nr["current_item_id"] is None:
            continue
        rows.append(nr)

    # 去重：同一个宝贝ID只取最后一条（以 Excel 最后出现为准）
    dedup: Dict[int, Dict[str, Any]] = {}
    for rr in rows:
        dedup[int(rr["current_item_id"])] = rr
    rows = list(dedup.values())

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        conn.autocommit = False

        # 确保字段存在
        ensure_publication_date_column(conn)

        if create_unique_index:
            ensure_indexes(conn)

        item_ids = [int(r["current_item_id"]) for r in rows]
        existing = load_existing_by_item_id(conn, item_ids)

        inserted = 0
        updated = 0
        skipped = 0

        with conn.cursor() as cur:
            for r in rows:
                cid = int(r["current_item_id"])
                if cid in existing:
                    old = existing[cid]
                    changes = diff_fields(r, old)
                    if not changes:
                        skipped += 1
                        continue

                    sets = ", ".join([f"{k}=%({k})s" for k in changes.keys()])
                    sql = f"""
                        UPDATE {CATALOG_TABLE}
                        SET {sets},
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %(id)s
                    """
                    params = dict(changes)
                    params["id"] = old["id"]
                    cur.execute(sql, params)
                    updated += 1
                else:
                    sql = f"""
                        INSERT INTO {CATALOG_TABLE}
                        (product_code, item_name, brand, category, list_price, current_item_id, publication_date)
                        VALUES
                        (%(product_code)s, %(item_name)s, %(brand)s, %(category)s, %(list_price)s, %(current_item_id)s, %(publication_date)s)
                    """
                    cur.execute(sql, r)
                    inserted += 1

        conn.commit()
        print(f"✅ 导入完成：inserted={inserted}, updated={updated}, skipped={skipped}")
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    # 示例：改成你本机路径
    excel_path = r"D:\TB\Reports\商品统计_20251230.xlsx"
    import_catalog_items_from_excel(excel_path, create_indexes=True)
