# -*- coding: utf-8 -*-
"""
按【商品编码】汇总库存，导出“总库存 < 阈值”的清单到 Excel。
列：渠道产品ID（清洗后）、商品编码、product_title、总库存

Pipeline 用法：
from export_low_stock_products import export_low_stock_for_brand
out_path = export_low_stock_for_brand("camper", threshold=5, prefer_binding_table=False)

可选：若你有外部绑定表（如 channel_binding(product_code, channel_product_id)），
把 prefer_binding_table=True 并确保表名传入 binding_table。
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

from config import BRAND_CONFIG  # 读取每个品牌的 TABLE_NAME / OUTPUT_DIR / PGSQL_CONFIG


def _sql_trim_id(expr: str) -> str:
    """
    生成对渠道ID做清洗的 SQL 片段：
    - TRIM 去首尾空白
    - 将前后方括号 [] 去掉
    - 将空字符串归一成 NULL 以便 MAX/COALESCE 正常工作
    """
    # 去空格 -> 去方括号 -> 归一为空
    return f"NULLIF(REGEXP_REPLACE(TRIM({expr}), '^\\[|\\]$', '', 'g'), '')"


def export_low_stock_for_brand(
    brand: str,
    threshold: int = 5,
    prefer_binding_table: bool = False,
    binding_table: str = "channel_binding",
) -> Path:
    """
    导出指定品牌 “总库存 < threshold” 的编码清单（按编码聚合）。

    Args:
        brand: 品牌名，如 "camper" / "clarks_jingya" / "barbour"
        threshold: 总库存阈值，默认 5
        prefer_binding_table: 若为 True，则优先从外部绑定表取渠道产品ID，失败再回退到品牌主表
        binding_table: 外部绑定表表名（需至少包含 product_code, channel_product_id 两列）

    Returns:
        输出 Excel 文件路径 Path
    """
    cfg = BRAND_CONFIG.get(brand.lower())
    if not cfg:
        raise ValueError(f"未在 config.BRAND_CONFIG 中找到品牌配置：{brand}")

    table = cfg["TABLE_NAME"]
    pg = cfg["PGSQL_CONFIG"]
    out_dir = Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{brand}_low_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # —— SQL 组装 —— #
    # 低库存集合
    low_stock_cte = f"""
    WITH low_stock AS (
        SELECT product_code,
               SUM(COALESCE(stock_count, 0)) AS total_stock
        FROM {table}
        GROUP BY product_code
        HAVING SUM(COALESCE(stock_count, 0)) < %s
    )
    """

    # 主表内清洗后的渠道ID与标题
    ci_id = _sql_trim_id("ci.channel_product_id")
    ci_title = "NULLIF(TRIM(ci.product_title), '')"

    if prefer_binding_table:
        # 外部绑定表清洗后的渠道ID
        cb_id = _sql_trim_id("cb.channel_product_id")
        sql = f"""
        {low_stock_cte}
        SELECT
            COALESCE(
                MAX({cb_id}),
                MAX({ci_id})
            ) AS "渠道产品ID",
            ls.product_code           AS "商品编码",
            MAX({ci_title})           AS product_title,
            ls.total_stock            AS "总库存"
        FROM low_stock ls
        LEFT JOIN {table} ci
               ON ci.product_code = ls.product_code
        LEFT JOIN {binding_table} cb
               ON cb.product_code = ls.product_code
        GROUP BY ls.product_code, ls.total_stock
        ORDER BY "总库存" ASC, "商品编码" ASC;
        """
    else:
        # 仅用品牌主表
        sql = f"""
        {low_stock_cte}
        SELECT
            MAX({ci_id})              AS "渠道产品ID",
            ls.product_code           AS "商品编码",
            MAX({ci_title})           AS product_title,
            ls.total_stock            AS "总库存"
        FROM low_stock ls
        LEFT JOIN {table} ci
               ON ci.product_code = ls.product_code
        GROUP BY ls.product_code, ls.total_stock
        ORDER BY "总库存" ASC, "商品编码" ASC;
        """

    # —— 执行查询 —— #
    with psycopg2.connect(**pg) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (threshold,))
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["渠道产品ID", "商品编码", "product_title", "总库存"])
    # 确保列顺序一致
    df = df.reindex(columns=["渠道产品ID", "商品编码", "product_title", "总库存"])

    # —— 导出 —— #
    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="低库存")
        meta = pd.DataFrame({
            "参数": ["品牌", "表名", "阈值", "prefer_binding_table", "binding_table", "导出时间"],
            "值": [brand, table, threshold, str(prefer_binding_table), binding_table, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        })
        meta.to_excel(writer, index=False, sheet_name="参数")

    return out_file
