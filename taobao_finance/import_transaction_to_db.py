import pandas as pd
import re
from pathlib import Path
from sqlalchemy import create_engine, text
from cfg.db_config import PGSQL_CONFIG

# ================== 配置 ==================
EXCEL_PATH = r"D:\OneDrive\Documentation\淘宝会计统计数据\ExportOrderList25827949225.xlsx"
# EXCEL_PATH = r"D:\OneDrive\Documentation\淘宝会计统计数据\淘宝历史交易数据.xlsx"
TABLE_NAME = "taobao_order_logistics"
# =========================================

DB_CONFIG = PGSQL_CONFIG   # ✅ 保留不动


def get_engine():
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    return create_engine(url)


def normalize_order_id(val):
    """订单号统一：去空格、去.0、保留数字字符串"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    s = re.sub(r"\.0$", "", s)
    s = re.sub(r"\s+", "", s)
    # 淘宝订单号一般是纯数字，这里只保留数字，避免带前缀
    s2 = re.sub(r"\D", "", s)
    return s2 if s2 else None


def parse_money(val):
    """金额统一转 numeric（支持¥、逗号、空）"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("¥", "").replace(",", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def pick_col(df: pd.DataFrame, candidates, required=False, field_name=""):
    """从候选列名里挑出第一个存在的列"""
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise KeyError(f"缺少必需字段[{field_name}]，候选列名：{candidates}，实际列名：{list(df.columns)}")
    return None


def upsert_dataframe(engine, df_out: pd.DataFrame):
    cols = list(df_out.columns)

    insert_cols_sql = ", ".join(cols) + ", imported_at"
    values_sql = ", ".join([f":{c}" for c in cols]) + ", NOW()"

    # 冲突时更新除 order_id 外字段；不覆盖鲸芽字段（避免被淘宝导入冲掉）
    update_cols = [c for c in cols if c != "order_id"]
    update_sql = ",\n            ".join([f"{c} = EXCLUDED.{c}" for c in update_cols] + ["imported_at = NOW()"])

    sql = text(f"""
        INSERT INTO {TABLE_NAME} ({insert_cols_sql})
        VALUES ({values_sql})
        ON CONFLICT (order_id) DO UPDATE SET
            {update_sql};
    """)

    records = df_out.to_dict(orient="records")
    batch_size = 1000
    with engine.begin() as conn:
        for i in range(0, len(records), batch_size):
            conn.execute(sql, records[i:i + batch_size])

    print(f"✅ UPSERT 完成：{len(records)} 条")


def import_transaction():
    excel_file = Path(EXCEL_PATH)
    if not excel_file.exists():
        raise FileNotFoundError(f"找不到文件: {EXCEL_PATH}")

    print("📥 读取 Excel:", excel_file.name)
    df = pd.read_excel(excel_file, dtype=str)
    df.columns = [str(c).strip().replace("\u3000", " ") for c in df.columns]
    print("📌 发现列名：", list(df.columns))

    # ========= 关键：兼容老/新列名（你关心的两个字段就在这里） =========
    col_order_id = pick_col(df, ["订单编号", "订单号", "主订单号", "交易订单号"], required=True, field_name="order_id")

    # ✅ 总金额（老表/新表可能叫：总金额/订单金额/实付金额/买家实付金额/交易金额）
    col_total_amount = pick_col(df, ["总金额", "订单金额", "实付金额", "买家实付金额", "交易金额", "成交金额"], required=False, field_name="total_amount")

    # ✅ 快递单号（老表/新表可能叫：物流单号/快递单号/运单号/快递运单号）
    col_tracking_no = pick_col(df, ["物流单号", "快递单号", "运单号", "快递运单号", "Tracking No"], required=False, field_name="tracking_no")

    # ✅ 快递公司（老表/新表可能叫：物流公司/快递公司/承运公司）
    col_logistics_company = pick_col(df, ["物流公司", "快递公司", "承运公司", "Logistics Company"], required=False, field_name="logistics_company")

    # 其它字段也做兼容（可按你实际表再补候选）
    col_payment_id = pick_col(df, ["支付单号", "支付号"], required=False, field_name="payment_id")
    col_payment_detail = pick_col(df, ["支付详情"], required=False, field_name="payment_detail")
    col_order_status = pick_col(df, ["订单状态", "交易状态"], required=False, field_name="order_status")
    col_merchant_note = pick_col(df, ["商家备注", "备注"], required=False, field_name="merchant_note")

    col_refund_amount = pick_col(df, ["退款金额"], required=False, field_name="refund_amount")
    col_compensation_amount = pick_col(df, ["主动赔付金额", "赔付金额"], required=False, field_name="compensation_amount")
    col_payout_amount = pick_col(df, ["确认收货打款金额", "打款金额"], required=False, field_name="payout_amount")

    def get_series(col):
        return df[col] if col else pd.Series([None] * len(df))

    # ========= 构造入库 df_out =========
    df_out = pd.DataFrame({
        "order_id": get_series(col_order_id).apply(normalize_order_id),

        "payment_id": get_series(col_payment_id),
        "payment_detail": get_series(col_payment_detail),

        # ✅ 重点：总金额/快递单号/快递公司
        "total_amount": get_series(col_total_amount).apply(parse_money),
        "order_status": get_series(col_order_status),

        "tracking_no": get_series(col_tracking_no).apply(lambda x: str(x).strip().replace("\u3000", " ") if pd.notna(x) else None),
        "logistics_company": get_series(col_logistics_company),
        "merchant_note": get_series(col_merchant_note),

        "refund_amount": get_series(col_refund_amount).apply(parse_money),
        "compensation_amount": get_series(col_compensation_amount).apply(parse_money),
        "payout_amount": get_series(col_payout_amount).apply(parse_money),

        "source_file": excel_file.name,
    })

    # 过滤没有订单号的行
    before = len(df_out)
    df_out = df_out[df_out["order_id"].notna() & (df_out["order_id"] != "")]
    after = len(df_out)
    if before != after:
        print(f"⚠️ 过滤无订单号行：{before - after} 条")

    # 提醒你是否找到关键列
    print(f"✅ order_id列: {col_order_id}")
    print(f"✅ total_amount列: {col_total_amount}")
    print(f"✅ tracking_no列: {col_tracking_no}")
    print(f"✅ logistics_company列: {col_logistics_company}")

    engine = get_engine()
    upsert_dataframe(engine, df_out)


if __name__ == "__main__":
    import_transaction()
