# get_channel_product_ids.py
#
# 用法：输入品牌名 + product_code 列表，返回对应的 channel_product_id 列表
# 输出文件只包含找到的 channel_product_id（跳过 NULL），并打印诊断报告

from typing import Dict, List, Optional, Sequence
import psycopg2

from config import PGSQL_CONFIG
from cfg.db_config import BRAND_TABLE


# ============================================================
# 内部工具
# ============================================================

def _dedupe_keep_order(items: Sequence[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ============================================================
# 核心查询函数（通用所有品牌）
# ============================================================

def get_channel_product_ids(
    brand_name: str,
    product_codes: Sequence[str],
    *,
    code_column: str = "product_code",
    channel_column: str = "channel_product_id",
) -> Dict[str, Optional[str]]:
    """
    查询 brand_name 对应表，返回 {product_code -> channel_product_id} 的字典。
    找不到或 DB 中为 NULL 的 code，对应值为 None。
    """
    brand = (brand_name or "").strip().lower()
    if brand not in BRAND_TABLE:
        raise ValueError(
            f"未知品牌 '{brand_name}'，请在 cfg/db_config.py 的 BRAND_TABLE 里添加"
        )

    table = BRAND_TABLE[brand]
    uniq_codes = _dedupe_keep_order(product_codes)

    if not uniq_codes:
        return {}

    result: Dict[str, Optional[str]] = {c: None for c in uniq_codes}

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            # 用 ANY(%s) 单次查询，避免 execute_values 分批导致只取最后一批结果
            sql = f"""
                SELECT DISTINCT ON ({code_column}) {code_column}, {channel_column}
                FROM {table}
                WHERE {code_column} = ANY(%s)
                  AND {channel_column} IS NOT NULL
            """
            cur.execute(sql, (uniq_codes,))
            rows = cur.fetchall()

            for code, ch_pid in rows:
                if ch_pid:
                    result[code] = str(ch_pid)
    finally:
        conn.close()

    return result


# ============================================================
# 主入口函数：读文件 -> 查询 -> 写文件 + 诊断报告
# ============================================================

def run_channel_product_id_query(
    brand_name: str,
    input_txt_path: str,
    output_txt_path: str,
    *,
    skip_not_found: bool = True,
):
    """
    1. 从 input_txt_path 读取 product_code（每行一个）
    2. 查询对应的 channel_product_id
    3. 输出到 output_txt_path
       - skip_not_found=True（默认）：只输出找到的 channel_product_id，每行一个
       - skip_not_found=False：所有 code 都输出，没找到的写空行
    4. 打印诊断报告
    """

    # 读取输入文件（自动去 BOM、去空行）
    with open(input_txt_path, "r", encoding="utf-8-sig") as f:
        product_codes = [line.strip() for line in f if line.strip()]

    if not product_codes:
        print("输入文件没有商品编码")
        return

    print(f"品牌: {brand_name}")
    print(f"输入 product_code 数量: {len(product_codes)}")

    # 查询
    mapping = get_channel_product_ids(brand_name=brand_name, product_codes=product_codes)

    # 统计
    found = {code: cid for code, cid in mapping.items() if cid is not None}
    not_found = [code for code, cid in mapping.items() if cid is None]

    # 写输出文件
    with open(output_txt_path, "w", encoding="utf-8") as f:
        if skip_not_found:
            for cid in found.values():
                f.write(f"{cid}\n")
        else:
            for code in product_codes:
                clean = (code or "").strip()
                cid = mapping.get(clean, "")
                f.write(f"{cid if cid else ''}\n")

    # 诊断报告
    print(f"找到 channel_product_id: {len(found)} 条")
    print(f"未找到（DB 无此 code 或 channel_product_id 为空）: {len(not_found)} 条")
    if not_found:
        preview = not_found[:10]
        print(f"  未找到的 code（前 {len(preview)} 条）: {preview}")
    print(f"输出文件: {output_txt_path}")


# ============================================================
# 直接运行示例
# ============================================================

if __name__ == "__main__":
    run_channel_product_id_query(
        brand_name="ecco",
        input_txt_path=r"G:\temp\ecco\codes.txt",
        output_txt_path=r"G:\temp\ecco\channel_ids.txt",
    )
