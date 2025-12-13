import hashlib
import json
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

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
def import_anna_file(filepath):
    if filepath.lower().endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    # ⚠️ 根据你 ANNA 实际表头微调
    df = df.rename(columns={
        "Authorised on": "authorised_on",
        "Amount": "amount",
        "Currency": "currency",
        "Counterparty": "counterparty",
        "Description": "description",
        "Category": "anna_category",
        "Order Number": "order_number",
        "Supplier": "supplier_name_norm"
    })

    records = []

    for _, row in df.iterrows():
        txn = {
            "anna_txn_uid": generate_txn_uid(row),
            "authorised_on": row.get("authorised_on"),
            "amount": row.get("amount"),
            "currency": row.get("currency", "GBP"),
            "counterparty": row.get("counterparty"),
            "description": row.get("description"),
            "anna_category": row.get("anna_category"),
            "supplier_name_norm": row.get("supplier_name_norm"),
            "order_number": normalize_order_number(row.get("order_number")),
            "raw_row_json": json.dumps(row.to_dict(), default=str)
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
            r["raw_row_json"]
        )
        for r in records
    ]

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()
    execute_values(cur, insert_sql, values)
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
