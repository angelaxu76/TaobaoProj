# -*- coding: utf-8 -*-
"""
从 barbour_products 表中导出符合 BARBOUR_COLOR_CODE_MAP 格式的颜色映射
保持原格式：
   "OL": {"en": "Olive", "zh": ""},

特点：
- 保留重复 key（因为你需要 Product Color 精准匹配）
- zh 为空，供你后续人工补充
- 输出到 barbour_color_map_generated.py
"""

from pathlib import Path
import psycopg2
from config import BARBOUR

PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]

# 输出文件
THIS_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = THIS_DIR / "barbour_color_map_generated.py"


def fetch_all_colors():
    sql = """
        SELECT DISTINCT
            SUBSTRING(product_code FROM 8 FOR 2) AS color_code,
            TRIM(color) AS color_name
        FROM barbour_products
        WHERE color IS NOT NULL AND color <> ''
        ORDER BY 1, 2;
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return rows


def generate_python_color_map(rows):
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write('"""\n')
        f.write("自动从 barbour_products 导出，不要手工修改\n")
        f.write("格式保持与 BARBOUR_COLOR_CODE_MAP 完全一致\n")
        f.write('"""\n\n')

        f.write("BARBOUR_COLOR_CODE_MAP_GENERATED = {\n")

        for code, name in rows:
            # 名字转义
            safe_name = name.replace("\\", "\\\\").replace('"', '\\"')

            f.write(f'    "{code}": {{"en": "{safe_name}", "zh": ""}},\n')

        f.write("}\n")

    print(f"✅ 已生成: {OUTPUT_FILE}")
    print(f"📦 共导出 {len(rows)} 条颜色映射（含重复 key）")


def main():
    print("⏳ 正在读取 barbour_products...")
    rows = fetch_all_colors()
    generate_python_color_map(rows)


if __name__ == "__main__":
    main()
