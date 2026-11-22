# -*- coding: utf-8 -*-
"""
一次性迁移：给各品牌库存表加 product_material / feature 字段（来自 TXT 的 Product Material / Feature）。

- 用途：羊绒等材质判断只看数据库即可，不依赖 TXT（TXT 会被流水线清空）
- 只加字段，不改现有数据；重复运行无副作用（IF NOT EXISTS）
- 加完后重新跑一次各品牌的 import_txt_to_db_supplier()，两列就会从 TXT 写入
- Barbour 不走这套导入（商品信息在 barbour_products），不处理
"""
import psycopg2
from config import BRAND_CONFIG

BRANDS = ["clarks", "camper", "geox", "ecco", "marksandspencer", "toast", "reiss"]


def add_material_feature_columns():
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
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS product_material TEXT")
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS feature TEXT")
                print(f"✅ {brand}: {table}.product_material / feature 已就绪")
        finally:
            conn.close()


if __name__ == "__main__":
    add_material_feature_columns()
