
import psycopg2
from config import PGSQL_CONFIG

def load_product_keywords():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT color_code, size, match_keywords FROM barbour_products")
        rows = cur.fetchall()
    conn.close()
    return rows  # List of (color_code, size, keywords)

def match_product(title: str, size: str):
    title = title.lower()
    candidates = load_product_keywords()
    for color_code, product_size, keywords in candidates:
        if product_size.lower() != size.lower():
            continue
        if all(kw in title for kw in keywords):
            return color_code, product_size
    return None, None
