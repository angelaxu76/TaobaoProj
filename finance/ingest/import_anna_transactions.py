import hashlib
import json
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from config import PGSQL_CONFIG  # 你的项目里应该已有


# ======================
# 数据库配置
# ======================
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "your_db",
    "user": "your_user",
    "password": "your_password"
}

# ======================
# 工具函数
# ======================
def normalize_order_number(val):
    if pd.isna(val):
        return None
    val = str(val).strip()
    if val.endswith(".0"):
        val = val[:-2]
    return val or None


def generate_txn_uid(row):
    raw = f"{row.get('authorised_on')}|{row.get('amount')}|{row.get('currency')}|{row.get('counterparty')}|{row.get('description')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ======================
# 主导入逻辑
# ======================
from pathlib import Path

def _safe_json_value(v):
    # pandas / numpy NaN, NaT -> None (JSON null)
    if v is None:
        return None
    if pd.isna(v):
        return None
    # pandas Timestamp -> ISO string
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    return v

def _pick_col(df, candidates):
    """Return the first existing column name from candidates, else None."""
    cols = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in cols:
            return cols[name.lower()]
    return None

def import_anna_file(filepath, show_headers=True):
    path = Path(filepath)  # 兼容 WindowsPath / str
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}, file={path}")

    # 1) 显示真实表头，方便你确认列名（只打印一次即可）
    if show_headers:
        print("[ANNA] Headers:", list(df.columns))

    # 2) 自动匹配列名（你不用死记 ANNA 导出到底叫啥）
    col_authorised = _pick_col(df, [
    "Authorised on", "Authorized on", "Authorised On",
    "Created", "Created at", "Created on", "Creation date",
    "Date", "Transaction date", "Transaction Date"
    ])

    col_amount     = _pick_col(df, ["Amount", "Money", "Value"])
    col_currency   = _pick_col(df, ["Currency"])
    col_party      = _pick_col(df, ["Counterparty", "Merchant", "Payee", "From", "To"])
    col_desc       = _pick_col(df, ["Description", "Reference", "Details"])
    col_cat        = _pick_col(df, ["Category", "ANNA category"])

    # 你自己补的列（如果你在 Excel 里已经加了）
    col_order      = _pick_col(df, ["Order Number", "Order", "order_number", "supplier_order_no"])
    col_supplier   = _pick_col(df, ["Supplier", "supplier_name_norm", "Supplier Name"])
    col_brand      = _pick_col(df, ["Description","Brand", "brand"])

    # 3) 生成 records（raw_row_json 彻底避免 NaN）
    records = []
    for _, row in df.iterrows():
        # 构造一个“标准化视图”给 generate_txn_uid 用
        std = {
            "authorised_on": row.get(col_authorised) if col_authorised else None,
            "amount": row.get(col_amount) if col_amount else None,
            "currency": row.get(col_currency) if col_currency else "GBP",
            "counterparty": row.get(col_party) if col_party else None,
            "description": row.get(col_desc) if col_desc else None
        }

        raw_dict = {k: _safe_json_value(v) for k, v in row.to_dict().items()}
        txn = {
            "anna_txn_uid": generate_txn_uid(std),
            "authorised_on": std["authorised_on"],
            "amount": std["amount"],
            "currency": std["currency"] or "GBP",
            "counterparty": std["counterparty"],
            "description": std["description"],
            "anna_category": row.get(col_cat) if col_cat else None,
            "supplier_name_norm": row.get(col_supplier) if col_supplier else None,
            "order_number": normalize_order_number(row.get(col_order)) if col_order else None,
            "brand": row.get(col_brand) if col_brand else None,
            "raw_row_json": json.dumps(raw_dict, ensure_ascii=False)
        }
        records.append(txn)

    insert_sql = """
        INSERT INTO public.anna_transactions (
            anna_txn_uid,
            authorised_on,
            amount,
            currency,
            counterparty,
            description,
            anna_category,
            supplier_name_norm,
            order_number,
            brand,
            raw_row_json
        )
        VALUES %s
        ON CONFLICT (anna_txn_uid) DO NOTHING
    """

    values = [
        (
            r["anna_txn_uid"],
            r["authorised_on"],
            r["amount"],
            r["currency"],
            r["counterparty"],
            r["description"],
            r["anna_category"],
            r["supplier_name_norm"],
            r["order_number"],
            r["brand"],
            r["raw_row_json"],
        )
        for r in records
    ]

    db = dict(PGSQL_CONFIG)
    if "database" in db and "dbname" not in db:
        db["dbname"] = db.pop("database")
    if db.get("host") in (None, "", "localhost"):
        db["host"] = "127.0.0.1"

    conn = psycopg2.connect(**db)
    cur = conn.cursor()
    execute_values(cur, insert_sql, values, page_size=500)
    conn.commit()
    cur.close()
    conn.close()

    print(f"Imported {len(values)} rows (duplicates ignored).")



# ======================
# CLI
# ======================
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python import_anna_transactions.py anna_export.xlsx")
        sys.exit(1)

    import_anna_file(sys.argv[1])
