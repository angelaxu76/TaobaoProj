# -*- coding: utf-8 -*-
"""
根据品牌 inventory 表，导出“库存总和过低 或 有货尺码数不足”的商品渠道产品ID列表
"""

import os
import psycopg2
import pandas as pd
from psycopg2.extras import DictCursor

from config import BRAND_CONFIG  # 使用你项目里的 BRAND_CONFIG / TABLE_NAME / PGSQL_CONFIG :contentReference[oaicite:0]{index=0}


def export_low_stock_channel_products(
    brand: str,
    stock_threshold: int,
    output_excel_path: str,
    max_allowed_size_count: int = 2,
):
    """
    从 brand 对应的 inventory 表中，找出满足以下条件之一的商品：
        1）单个商品编码的库存总和 < stock_threshold
        2）有货的尺码数量 <= max_allowed_size_count

    然后导出一个只包含一列【渠道产品ID】的 Excel 文件。

    参数：
        brand: 品牌名，如 "camper" / "ecco" / "clarks" / "geox" / "clarks_jingya" 等
        stock_threshold: 总库存阈值，如 3
        output_excel_path: 输出 Excel 路径，例如 D:/TB/Products/camper/low_stock.xlsx
        max_allowed_size_count: 有货尺码最大允许数量，默认为 2。
                                例：默认 2 时，有 0/1/2 个尺码有货的商品会进入列表。
    """

    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 未知品牌: {brand}")

    brand_cfg = BRAND_CONFIG[brand]
    table_name = brand_cfg["TABLE_NAME"]       # 如 camper_inventory / ecco_inventory 等 :contentReference[oaicite:1]{index=1}
    pgsql = brand_cfg["PGSQL_CONFIG"]

    # 创建输出目录
    out_dir = os.path.dirname(output_excel_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # 注意：
    #   - 使用 stock_count 统计总库存和有货尺码数量
    #   - 假设所有 inventory 表结构与 camper_inventory 一致（都有 stock_count / channel_product_id）:contentReference[oaicite:2]{index=2}
    sql = f"""
        WITH stock_agg AS (
            SELECT
                product_code,
                MAX(channel_product_id) AS channel_product_id,
                SUM(COALESCE(stock_count, 0)) AS total_stock,
                COUNT(*) FILTER (WHERE stock_count > 0) AS available_size_count
            FROM {table_name}
            GROUP BY product_code
        )
        SELECT
            channel_product_id
        FROM stock_agg
        WHERE
            (
                total_stock < %s
                OR available_size_count <= %s
            )
            AND channel_product_id IS NOT NULL
            AND channel_product_id <> ''
        ORDER BY channel_product_id;
    """

    conn = None
    try:
        conn = psycopg2.connect(**pgsql)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (stock_threshold, max_allowed_size_count))
            rows = cur.fetchall()

        channel_ids = {row["channel_product_id"] for row in rows}  # 去重
        channel_ids = sorted(channel_ids)

        df = pd.DataFrame({"渠道产品ID": channel_ids})
        df.to_excel(output_excel_path, index=False)

        print(
            f"✅ 品牌={brand} | 阈值: 总库存<{stock_threshold} "
            f"或 有货尺码数≤{max_allowed_size_count} | 导出 {len(channel_ids)} 条渠道产品ID -> {output_excel_path}"
        )

    except Exception as e:
        print(f"❌ 导出失败: {e}")
        raise
    finally:
        if conn:
            conn.close()
