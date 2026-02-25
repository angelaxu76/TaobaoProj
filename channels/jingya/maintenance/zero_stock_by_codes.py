# zero_stock_by_codes.py
#
# 将指定 product_code 列表对应的所有 SKU 库存在数据库中设为 0。
# 典型用途：手动下架"淘宝长期无浏览/无点击"的商品。
#
# 用法：
#   from channels.jingya.maintenance.zero_stock_by_codes import zero_stock_by_codes
#   zero_stock_by_codes("camper", input_txt_path=r"D:\temp\offline_codes.txt")

from typing import Sequence, List
import psycopg2

from config import PGSQL_CONFIG
from cfg.db_config import BRAND_TABLE


def _dedupe_keep_order(items: Sequence[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = (x or "").strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def zero_stock_by_codes(
    brand_name: str,
    input_txt_path: str,
    *,
    code_column: str = "product_code",
):
    """
    从 input_txt_path 读取 product_code（每行一个），
    将对应品牌库存表中所有匹配行的 stock_count 更新为 0。

    Args:
        brand_name:      品牌名，如 "camper" / "ecco" / "geox"
        input_txt_path:  包含 product_code 的 TXT 文件路径（每行一个编码）
        code_column:     数据库中商品编码列名，默认 "product_code"
    """
    brand = (brand_name or "").strip().lower()
    if brand not in BRAND_TABLE:
        raise ValueError(
            f"未知品牌 '{brand_name}'，请在 cfg/db_config.py 的 BRAND_TABLE 里添加"
        )

    with open(input_txt_path, "r", encoding="utf-8-sig") as f:
        product_codes = [line.strip() for line in f if line.strip()]

    if not product_codes:
        print("输入文件没有商品编码")
        return

    uniq_codes = _dedupe_keep_order(product_codes)
    table = BRAND_TABLE[brand]

    print(f"品牌: {brand_name}")
    print(f"输入 product_code: {len(product_codes)} 条（去重后 {len(uniq_codes)} 条）")

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            sql = f"""
                UPDATE {table}
                SET stock_count = 0
                WHERE {code_column} = ANY(%s)
            """
            cur.execute(sql, (uniq_codes,))
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    print(f"✅ 已将 {affected} 行（{len(uniq_codes)} 个商品编码的所有尺码）stock_count 设为 0")
