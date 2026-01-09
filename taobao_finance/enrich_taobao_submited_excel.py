# enrich_tax_excel_from_db.py
import argparse
import os
import re
from typing import List, Optional, Dict, Any

import pandas as pd
from sqlalchemy import create_engine, text

from cfg.db_config import PGSQL_CONFIG


TABLE_NAME = "taobao_order_logistics"

# 可能的“订单号”列名候选（税务推送Excel里经常会不同）
ORDER_ID_COL_CANDIDATES = [
    "订单编号",
    "订单号",
    "淘宝订单号",
    "主订单号",
    "交易订单号",
    "订单ID",
    "Order ID",
]

DB_CONFIG = PGSQL_CONFIG   # ✅ 关键行
def get_engine():
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    return create_engine(url)

def normalize_order_id(x) -> Optional[str]:
    """统一订单号：去空格、去末尾 .0（Excel常见）、保持字符串"""
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = re.sub(r"\.0$", "", s)
    s = re.sub(r"\s+", "", s)
    return s if s else None


def detect_order_id_col(df: pd.DataFrame) -> str:
    for c in ORDER_ID_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise KeyError(
        f"未找到订单号列。候选列名：{ORDER_ID_COL_CANDIDATES}\n"
        f"当前Excel列名：{list(df.columns)}"
    )


def chunk_list(items: List[str], size: int = 1000) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_order_info(engine, order_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    从 taobao_order_logistics 批量取数。
    返回 dict: {order_id: {sales_mode, jingya_profit, total_amount, tracking_no, logistics_company}}
    """
    if not order_ids:
        return {}

    result_map: Dict[str, Dict[str, Any]] = {}

    sql = text(f"""
        SELECT
            order_id,
            sales_mode,
            jingya_profit,
            total_amount,
            tracking_no,
            logistics_company
        FROM {TABLE_NAME}
        WHERE order_id = ANY(:order_ids)
    """)

    with engine.begin() as conn:
        # 分批查询，避免参数过大
        for batch in chunk_list(order_ids, 3000):
            rows = conn.execute(sql, {"order_ids": batch}).mappings().all()
            for r in rows:
                oid = r["order_id"]
                result_map[str(oid)] = {
                    "sales_mode": r.get("sales_mode"),
                    "jingya_profit": r.get("jingya_profit"),
                    "total_amount": r.get("total_amount"),
                    "tracking_no": r.get("tracking_no"),
                    "logistics_company": r.get("logistics_company"),
                }

    return result_map


def enrich_excel(input_path: str, output_path: Optional[str] = None) -> str:
    df = pd.read_excel(input_path, dtype=str)

    order_col = detect_order_id_col(df)
    df["_order_id_norm"] = df[order_col].apply(normalize_order_id)

    order_ids = (
        df["_order_id_norm"]
        .dropna()
        .unique()
        .tolist()
    )

    engine = get_engine()
    order_info_map = fetch_order_info(engine, order_ids)

    # 新增四列（先空着）
    df["经营模式"] = ""
    df["真实金额"] = ""
    df["tracking_no"] = ""
    df["logistics_company"] = ""

    # 回填
    not_found = 0
    for idx, oid in df["_order_id_norm"].items():
        if not oid:
            continue

        info = order_info_map.get(oid)
        if not info:
            not_found += 1
            # 找不到就默认普通（你也可以改成留空）
            df.at[idx, "经营模式"] = "普通"
            continue

        sales_mode_db = (info.get("sales_mode") or "").strip()
        is_distribution = (sales_mode_db == "分销")

        df.at[idx, "经营模式"] = "分销" if is_distribution else "普通"

        # 真实金额：分销取利润，普通取总额
        real_amount = info.get("jingya_profit") if is_distribution else info.get("total_amount")

        # 转字符串写入（避免科学计数法/空值）
        df.at[idx, "真实金额"] = "" if real_amount is None else str(real_amount)

        # tracking / company
        df.at[idx, "tracking_no"] = "" if info.get("tracking_no") is None else str(info.get("tracking_no"))
        df.at[idx, "logistics_company"] = "" if info.get("logistics_company") is None else str(info.get("logistics_company"))

    # 输出路径默认：原文件名 + _enriched.xlsx
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_enriched{ext if ext else '.xlsx'}"

    # 清理内部列
    df.drop(columns=["_order_id_norm"], inplace=True)

    df.to_excel(output_path, index=False)

    print(f"✅ 输入文件: {input_path}")
    print(f"✅ 输出文件: {output_path}")
    print(f"ℹ️ 订单号列: {order_col}")
    print(f"ℹ️ 订单数(去重): {len(order_ids)}，未在DB匹配到的行数: {not_found}")

    return output_path


def main():
    enrich_excel(r"D:\OneDrive\Documentation\淘宝会计统计数据\202511.xlsx", r"D:\OneDrive\Documentation\淘宝会计统计数据\202511_enrich.xlsx")


if __name__ == "__main__":
    main()
