
import psycopg2
from config import PGSQL_CONFIG
from datetime import datetime

def insert_offer_record(color_code, size, site_name, url, price, stock_status):
    can_order = stock_status.lower() in ["in stock", "available", "limited stock"]
    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO offers (color_code, size, site_name, offer_url, price_gbp, stock_status, can_order, last_checked)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (color_code, size, site_name)
            DO UPDATE SET
              price_gbp = EXCLUDED.price_gbp,
              stock_status = EXCLUDED.stock_status,
              can_order = EXCLUDED.can_order,
              last_checked = NOW()
        """, (
            color_code, size, site_name, url, price, stock_status, can_order
        ))
    conn.commit()
    conn.close()
