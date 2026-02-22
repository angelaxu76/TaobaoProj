# -*- coding: utf-8 -*-
"""
脚本功能：
从 barbour_products 读取所有颜色，并导入 barbour_color_map 表。

用法（在项目根目录）：
    python -m brands.barbour.tools.export_barbour_color_map
"""

import re
import psycopg2
from pathlib import Path
from config import BARBOUR


# ---------------------------------------
# 1. 标准化颜色名称 → norm_key
# ---------------------------------------
def build_norm_key(raw: str) -> str:
    """
    生成 norm_key：
    - 全小写
    - 所有非字母变空格
    - 拆成单词
    - 单词去重、排序
    - 拼成字符串
    """
    if not raw:
        return ""

    s = raw.lower().strip()
    s = re.sub(r"[^a-z]+", " ", s)
    tokens = [t for t in s.split() if t]

    if not tokens:
        return ""

    tokens = sorted(set(tokens))
    return " ".join(tokens)


# ---------------------------------------
# 2. 从 barbour_products 中抓取颜色
# ---------------------------------------
def fetch_colors_from_products(conn):
    sql = """
        SELECT DISTINCT
            SUBSTRING(product_code FROM 8 FOR 2) AS color_code,
            TRIM(color) AS color_name
        FROM barbour_products
        WHERE color IS NOT NULL AND color <> ''
        ORDER BY 1, 2;
    """

    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


# ---------------------------------------
# 3. 插入 barbour_color_map
# ---------------------------------------
def insert_color_map(conn, code, raw_name, norm_key):
    sql = """
        INSERT INTO barbour_color_map (color_code, raw_name, norm_key, source, is_confirmed)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (code, raw_name, norm_key, "products", False))


# ---------------------------------------
# 4. 主逻辑
# ---------------------------------------
def main():
    print("🔄 正在连接数据库...")
    conn = psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

    print("📦 从 barbour_products 读取颜色列表...")
    rows = fetch_colors_from_products(conn)
    print(f"📊 共发现 {len(rows)} 条颜色组合（不含重复）")

    inserted = 0
    for code, raw in rows:
        norm_key = build_norm_key(raw)
        insert_color_map(conn, code, raw, norm_key)
        inserted += 1

    conn.commit()
    conn.close()

    print("✅ 导入完成!")
    print(f"➡️ 共写入 {inserted} 条记录（重复的已自动跳过）")
    print("📁 表：barbour_color_map 已就绪。")


if __name__ == "__main__":
    main()
