import pandas as pd
import psycopg2
from config import PGSQL_CONFIG

# === 支持 XS-3XL、8-20、36-52 三类尺码段 ===
LETTER_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]

def parse_size_range(size_range):
    size_range = str(size_range).strip().upper()
    if "-" not in size_range:
        return [size_range]

    start, end = size_range.split("-", 1)

    # 数字尺码（女款或男士英寸）
    if start.isdigit() and end.isdigit():
        start, end = int(start), int(end)
        return [str(i) for i in range(start, end + 1, 2)]

    # 字母尺码（XS-3XL）
    if start in LETTER_SIZES and end in LETTER_SIZES:
        s_idx = LETTER_SIZES.index(start)
        e_idx = LETTER_SIZES.index(end)
        return LETTER_SIZES[s_idx:e_idx + 1]

    raise ValueError(f"无法识别尺码范围: {size_range}")

def extract_keywords(style_name):
    COMMON_WORDS = {"jacket", "coat", "gilet", "vest", "shirt", "top"}
    return [w.lower() for w in style_name.split() if w.lower() not in COMMON_WORDS]

def import_from_excel(path):
    df = pd.read_excel(path)
    required = {"color_code", "style_name", "color", "size_range"}
    if not required.issubset(df.columns):
        raise ValueError(f"缺少必要列，必须包含: {required}")

    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        total = 0
        for _, row in df.iterrows():
            color_code = str(row["color_code"]).strip()
            style_name = str(row["style_name"]).strip()
            color = str(row["color"]).strip()
            size_range = str(row["size_range"]).strip()
            sizes = parse_size_range(size_range)
            keywords = extract_keywords(style_name)

            for size in sizes:
                cur.execute("""
                    INSERT INTO barbour_products (color_code, style_name, color, size, match_keywords)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (color_code, size) DO NOTHING
                """, (color_code, style_name, color, size, keywords))
                total += 1

    conn.commit()
    conn.close()
    print(f"✅ 导入完成，共插入 {total} 条记录")

if __name__ == "__main__":
    excel_path = r"D:\TB\Products\barbour\manual_barbour_products_template.xlsx"  # 你保存的 Excel 路径
    import_from_excel(excel_path)
