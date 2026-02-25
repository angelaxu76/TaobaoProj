from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values, Json

# ✅ 从你项目配置读取
from cfg.db_config import PGSQL_CONFIG


# =========================
# 固定配置
# =========================
TABLE_NAME = "product_metrics_daily"


# =========================
# Excel → DB 严格字段映射
# =========================
COLUMN_MAP: Dict[str, str] = {
    # keys
    "统计日期": "stat_date",
    "商品ID": "item_id",
    "店铺名称": "store_name",

    # 成交结果
    "支付金额": "pay_amount",
    "支付件数": "pay_qty",
    "支付人数": "pay_buyer_cnt",
    "成功退款金额": "refund_amount",

    # 行为漏斗
    "加购件数": "cart_qty",
    "加购人数": "cart_buyer_cnt",
    "商品访客数": "visitors",
    "商品浏览量": "pageviews",
    "支付转化率": "pay_cvr",

    # 价值指标
    "客单价": "aov",
    "支付老客数": "old_buyer_cnt",
    "商品收藏人数": "fav_cnt",
    "UV价值": "uv_value",

    # 流量拆分
    "平台流量": "platform_visitors",
    "平台流量占比": "platform_visitors_share",

    "搜索访客数": "search_visitors",
    "搜索加购人数": "search_cart_buyer_cnt",
    "搜索支付金额": "search_pay_amount",
    "搜索支付件数": "search_pay_qty",
    "搜索支付人数": "search_pay_buyer_cnt",

    "推荐访客数": "recommend_visitors",
    "推荐加购人数": "recommend_cart_buyer_cnt",
    "推荐支付金额": "recommend_pay_amount",
    "推荐支付件数": "recommend_pay_qty",

    "关键词推广访客数": "kwpromo_visitors",
    "关键词推广加购人数": "kwpromo_cart_buyer_cnt",
    "关键词推广支付金额": "kwpromo_pay_amount",
    "关键词推广支付人数": "kwpromo_pay_buyer_cnt",
}

REQUIRED_EXCEL_COLS = ["统计日期", "商品ID", "店铺名称"]


# =========================
# 类型转换工具
# =========================
def _is_empty(x: Any) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and pd.isna(x):
        return True
    if isinstance(x, str) and x.strip() == "":
        return True
    return False


def to_date(x: Any):
    return pd.to_datetime(x).date()


def to_int(x: Any) -> Optional[int]:
    if _is_empty(x):
        return None
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None


def to_decimal(x: Any) -> Optional[Decimal]:
    if _is_empty(x):
        return None
    s = str(x).strip().replace(",", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    return Decimal(s) if s else None


def to_ratio(x: Any) -> Optional[Decimal]:
    if _is_empty(x):
        return None
    s = str(x).strip()
    try:
        return Decimal(s[:-1]) / Decimal("100") if s.endswith("%") else Decimal(s)
    except Exception:
        return None


DECIMAL_FIELDS = {
    "pay_amount", "refund_amount", "aov", "uv_value",
    "search_pay_amount", "recommend_pay_amount", "kwpromo_pay_amount",
}
INT_FIELDS = {
    "item_id",
    "pay_qty", "pay_buyer_cnt",
    "cart_qty", "cart_buyer_cnt",
    "visitors", "pageviews",
    "old_buyer_cnt", "fav_cnt",
    "platform_visitors",
    "search_visitors", "search_cart_buyer_cnt",
    "search_pay_qty", "search_pay_buyer_cnt",
    "recommend_visitors", "recommend_cart_buyer_cnt", "recommend_pay_qty",
    "kwpromo_visitors", "kwpromo_cart_buyer_cnt", "kwpromo_pay_buyer_cnt",
}
RATIO_FIELDS = {"pay_cvr", "platform_visitors_share"}


def normalize_db_value(db_col: str, val: Any) -> Any:
    if db_col == "stat_date":
        return to_date(val)
    if db_col == "store_name":
        return None if _is_empty(val) else str(val).strip()
    if db_col in INT_FIELDS:
        return to_int(val)
    if db_col in DECIMAL_FIELDS:
        return to_decimal(val)
    if db_col in RATIO_FIELDS:
        return to_ratio(val)
    return val


# =========================
# Excel 处理
# =========================
def load_excel(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    return df.where(pd.notna(df), None)


def validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_EXCEL_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少必需列: {missing}")


def row_to_raw_metrics(row: pd.Series) -> Dict[str, Any]:
    return {
        str(k): (None if _is_empty(v) else v.isoformat() if isinstance(v, pd.Timestamp) else v)
        for k, v in row.items()
    }


def build_rows(df: pd.DataFrame) -> List[Tuple]:
    rows: List[Tuple] = []
    for _, r in df.iterrows():
        values = []
        for excel_col, db_col in COLUMN_MAP.items():
            values.append(normalize_db_value(db_col, r.get(excel_col)))
        values.append(Json(row_to_raw_metrics(r)))
        rows.append(tuple(values))
    return rows


# =========================
# 写库（Upsert）
# =========================
def upsert_rows(conn, rows: List[Tuple], batch_size: int = 2000) -> int:
    if not rows:
        return 0

    insert_cols = list(COLUMN_MAP.values()) + ["raw_metrics"]
    conflict_key = ["stat_date", "item_id", "store_name"]
    set_cols = [c for c in insert_cols if c not in conflict_key]

    sql = f"""
    INSERT INTO {TABLE_NAME} ({", ".join(insert_cols)})
    VALUES %s
    ON CONFLICT ({", ".join(conflict_key)})
    DO UPDATE SET
      {", ".join(f"{c}=EXCLUDED.{c}" for c in set_cols)},
      updated_at = now()
    ;
    """

    total = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            execute_values(cur, sql, chunk, page_size=1000)
            total += len(chunk)
    return total


# =========================
# ✅ 对外暴露的主函数
# =========================
def import_product_metrics_daily(excel_path: str) -> int:
    """
    外部调用入口：
        import_product_metrics_daily(r"D:\\xxx\\202512.xlsx")
    """
    df = load_excel(excel_path)
    validate_columns(df)
    rows = build_rows(df)

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        conn.autocommit = False
        count = upsert_rows(conn, rows)
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =========================
# CLI / 单独运行
# =========================
if __name__ == "__main__":
    # 示例（你可删）
    path = r"D:\TB\analytics\input_data\daily_metrics\252506.xlsx"
    n = import_product_metrics_daily(path)
    print(f"✅ 导入完成：{n} 行")
