# -*- coding: utf-8 -*-
"""
一次性迁移：给各品牌库存表加 color 字段（中文颜色）。

- 只加字段，不改现有数据；重复运行无副作用（IF NOT EXISTS）
- 加完后重新跑一次各品牌的 import_txt_to_db_supplier()，color 就会从 TXT 写入
- Barbour 不走这套导入（颜色在 barbour_products.color），不处理
"""
import psycopg2
from config import BRAND_CONFIG

BRANDS = ["clarks", "camper", "geox", "ecco", "marksandspencer", "toast", "reiss"]


def add_color_column():
    for brand in BRANDS:
        cfg = BRAND_CONFIG[brand]
        table = cfg["TABLE_NAME"]
        conn = psycopg2.connect(**cfg["PGSQL_CONFIG"])
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s)", (table,))
                if cur.fetchone()[0] is None:
                    print(f"⏭️ {brand}: 表 {table} 不存在，跳过")
                    continue
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS color VARCHAR(100)")
                print(f"✅ {brand}: {table}.color 已就绪")
        finally:
            conn.close()


if __name__ == "__main__":
    add_color_column()
