# import_jingya_to_db.py
import re
import sys
import pandas as pd
from sqlalchemy import create_engine, text
from cfg.db_config import PGSQL_CONFIG


# ================== 配置 ==================
JINGYA_EXCEL_PATH = r"D:\OneDrive\Documentation\淘宝会计统计数据\jingya_202512.xlsx"
TABLE_NAME = "taobao_order_logistics"

ORDER_ID_COL = "消费者主订单号"

# ⚠️ 兼容多个版本的“分销利润字段名”
PROFIT_COL_CANDIDATES = [
    "分销单子单代购费（代购推广）",   # 老版本
    "鲸芽订单运营服务费",           # 新版本（你刚提到）
]
# =========================================

DB_CONFIG = PGSQL_CONFIG   # ✅ 关键行

def get_engine():
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    return create_engine(url)


def normalize_order_id(x):
    if x is None:
        return None
    s = str(x).strip()
    s = re.sub(r"\.0$", "", s)
    s = re.sub(r"\s+", "", s)
    return s if s else None


def parse_money(x):
    if x is None:
        return 0.0
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace("¥", "").replace(",", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def detect_profit_column(df: pd.DataFrame) -> str:
    """自动识别鲸芽利润列"""
    for col in PROFIT_COL_CANDIDATES:
        if col in df.columns:
            print(f"✅ 使用鲸芽利润列：{col}")
            return col
    raise KeyError(
        f"未找到鲸芽利润列，候选列为：{PROFIT_COL_CANDIDATES}\n"
        f"当前Excel列有：{list(df.columns)}"
    )


def import_jingya_profit(excel_path: str):
    print(f"📥 读取鲸芽Excel: {excel_path}")
    df = pd.read_excel(excel_path, dtype=str)

    if ORDER_ID_COL not in df.columns:
        raise KeyError(f"鲸芽表缺少列：{ORDER_ID_COL}")

    profit_col = detect_profit_column(df)

    df["order_id"] = df[ORDER_ID_COL].apply(normalize_order_id)
    df["jingya_profit"] = df[profit_col].apply(parse_money)

    df = df[df["order_id"].notna()].copy()

    # 同一订单号可能多行，按订单号汇总
    agg = df.groupby("order_id", as_index=False)["jingya_profit"].sum()

    print(f"📊 鲸芽订单数（按订单号汇总）: {len(agg)}")

    engine = get_engine()

    update_sql = text(f"""
        UPDATE {TABLE_NAME}
        SET
            is_jingya_order = TRUE,
            sales_mode = '分销',
            jingya_profit = :profit
        WHERE order_id = :order_id
    """)

    matched_orders = 0
    matched_rows = 0

    with engine.begin() as conn:
        for _, row in agg.iterrows():
            res = conn.execute(
                update_sql,
                {
                    "order_id": row["order_id"],
                    "profit": float(row["jingya_profit"]),
                }
            )
            if res.rowcount and res.rowcount > 0:
                matched_orders += 1
                matched_rows += res.rowcount

    print(f"✅ 匹配到的订单号数: {matched_orders}")
    print(f"✅ 实际更新的数据库行数: {matched_rows}")
    print("🎉 鲸芽利润导入完成")


if __name__ == "__main__":
    import_jingya_profit(JINGYA_EXCEL_PATH)
