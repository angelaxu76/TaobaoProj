from turtle import Turtle
from xml.etree.ElementTree import TreeBuilder
import psycopg2
from config import PGSQL_CONFIG


from brands.barbour.core.learn_color_map_from_products import (
    fetch_best_mappings,
    upsert,
    show_conflicts,
)

def run_color_map_learning():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        rows = fetch_best_mappings(
            conn,
            min_total=5,
            min_ratio=0.7,
        )

        if not rows:
            print("No high-confidence color mappings found.")
            return

        upsert(
            conn,
            rows,
            source="learned_from_products",
            dry_run=False,
        )

        # 可选：打印冲突色
        show_conflicts(conn, limit=50)

    finally:
        conn.close()


if __name__ == "__main__":
    run_color_map_learning()
