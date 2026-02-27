# -*- coding: utf-8 -*-

# 根据品牌 inventory 表，导出低库存商品清单。提供两个函数：
# - export_low_stock_channel_products()：维护用，双条件过滤（总库存 + 有货尺码数）
# - export_low_stock_for_brand()：Pipeline 用，单阈值过滤，支持绑定表，输出带时间戳文件

import os
from pathlib import Path
from datetime import datetime
import psycopg2
import pandas as pd
from psycopg2.extras import DictCursor, RealDictCursor

from config import BRAND_CONFIG  # 使用你项目里的 BRAND_CONFIG / TABLE_NAME / PGSQL_CONFIG


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

    然后导出一个包含 4 列的 Excel 文件：
        Product Code / 总库存 / 有货尺码数 / 渠道产品ID
    """

    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 未知品牌: {brand}")

    brand_cfg = BRAND_CONFIG[brand]
    table_name = brand_cfg["TABLE_NAME"]       # 如 camper_inventory / ecco_inventory 等
    pgsql = brand_cfg["PGSQL_CONFIG"]

    # 创建输出目录
    out_dir = os.path.dirname(output_excel_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # 聚合每个 product_code 的库存、尺码数和 channel_product_id
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
            product_code,
            total_stock,
            available_size_count,
            channel_product_id
        FROM stock_agg
        WHERE
            (
                total_stock < %s
                OR available_size_count <= %s
            )
            AND channel_product_id IS NOT NULL
            AND channel_product_id <> ''
        ORDER BY product_code;
    """

    conn = None
    try:
        conn = psycopg2.connect(**pgsql)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (stock_threshold, max_allowed_size_count))
            rows = cur.fetchall()

        # 每一行对应一个 product_code
        records = []
        for row in rows:
            records.append({
                "Product Code": row["product_code"],
                "总库存": row["total_stock"],
                "有货尺码数": row["available_size_count"],
                "渠道产品ID": row["channel_product_id"],
            })

        df = pd.DataFrame(records)
        df.to_excel(output_excel_path, index=False)

        print(
            f"✅ 品牌={brand} | 阈值: 总库存<{stock_threshold} "
            f"或 有货尺码数≤{max_allowed_size_count} | 导出 {len(df)} 条商品 -> {output_excel_path}"
        )

    except Exception as e:
        print(f"❌ 导出失败: {e}")
        raise
    finally:
        if conn:
            conn.close()


def _sql_trim_id(expr: str) -> str:
    return f"NULLIF(REGEXP_REPLACE(TRIM({expr}), '^\\[|\\]$', '', 'g'), '')"


def export_low_stock_for_brand(
    brand: str,
    threshold: int = 5,
    prefer_binding_table: bool = False,
    binding_table: str = "channel_binding",
) -> Path:
    """
    Pipeline 用：导出指定品牌"总库存 < threshold"的编码清单（按编码聚合）。
    输出 Excel 含列：渠道产品ID、商品编码、product_title、总库存
    """
    cfg = BRAND_CONFIG.get(brand.lower())
    if not cfg:
        raise ValueError(f"未在 config.BRAND_CONFIG 中找到品牌配置：{brand}")

    table = cfg["TABLE_NAME"]
    pg = cfg["PGSQL_CONFIG"]
    out_dir = Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{brand}_low_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    low_stock_cte = f"""
    WITH low_stock AS (
        SELECT product_code,
               SUM(COALESCE(stock_count, 0)) AS total_stock
        FROM {table}
        GROUP BY product_code
        HAVING SUM(COALESCE(stock_count, 0)) < %s
    )
    """

    ci_id = _sql_trim_id("ci.channel_product_id")
    ci_title = "NULLIF(TRIM(ci.product_title), '')"

    if prefer_binding_table:
        cb_id = _sql_trim_id("cb.channel_product_id")
        sql = f"""
        {low_stock_cte}
        SELECT
            COALESCE(MAX({cb_id}), MAX({ci_id})) AS "渠道产品ID",
            ls.product_code AS "商品编码",
            MAX({ci_title}) AS product_title,
            ls.total_stock  AS "总库存"
        FROM low_stock ls
        LEFT JOIN {table} ci ON ci.product_code = ls.product_code
        LEFT JOIN {binding_table} cb ON cb.product_code = ls.product_code
        GROUP BY ls.product_code, ls.total_stock
        ORDER BY "总库存" ASC, "商品编码" ASC;
        """
    else:
        sql = f"""
        {low_stock_cte}
        SELECT
            MAX({ci_id})    AS "渠道产品ID",
            ls.product_code AS "商品编码",
            MAX({ci_title}) AS product_title,
            ls.total_stock  AS "总库存"
        FROM low_stock ls
        LEFT JOIN {table} ci ON ci.product_code = ls.product_code
        GROUP BY ls.product_code, ls.total_stock
        ORDER BY "总库存" ASC, "商品编码" ASC;
        """

    with psycopg2.connect(**pg) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (threshold,))
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["渠道产品ID", "商品编码", "product_title", "总库存"])
    df = df.reindex(columns=["渠道产品ID", "商品编码", "product_title", "总库存"])

    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="低库存")
        meta = pd.DataFrame({
            "参数": ["品牌", "表名", "阈值", "prefer_binding_table", "binding_table", "导出时间"],
            "值": [brand, table, threshold, str(prefer_binding_table), binding_table,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        })
        meta.to_excel(writer, index=False, sheet_name="参数")

    return out_file

