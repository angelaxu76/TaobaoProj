import pandas as pd
from pathlib import Path

def sql_quote(value: str) -> str:
    """Quote string for SQL single-quoted literal, doubling internal single quotes."""
    return "'" + value.replace("'", "''") + "'"

def generate_select_sql_from_excel(
    excel_path: str,
    column_name: str = "商品编码",
    table_name: str = "barbour_inventory",
    size_regex: str = r"^(XS|S|M|L|XL|XXL|3XL|4XL)$",
    chunk_size: int = 500,
    output_sql_path: str | None = None,
) -> dict:
    """
    读取 Excel -> 提取去重后的商品编码 -> 生成一条或多条 SELECT 语句（按 chunk_size 分段） -> 写出到 .sql 文件
    返回: {'total_codes', 'statements_count', 'output_sql_path', 'preview'}
    """
    excel_path = Path(excel_path)
    assert excel_path.exists(), f"Excel not found: {excel_path}"
    
    # 读第一张表；如需指定 sheet，可在调用时设置 sheet_name
    df = pd.read_excel(excel_path, sheet_name=0)
    if column_name not in df.columns:
        raise KeyError(f"Column '{column_name}' not found. Available columns: {list(df.columns)}")
    
    # 提取编码并清洗
    codes = (
        df[column_name]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    # 保序去重
    codes = list(dict.fromkeys(codes))

    # 分段（避免 IN 过长）
    def chunk(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    statements = []
    for part in chunk(codes, chunk_size):
        in_list = ",".join(sql_quote(c) for c in part)
        sql = (
            "SELECT DISTINCT product_code\n"
            f"FROM {table_name}\n"
            f"WHERE size ~ '{size_regex}'\n"
            f"  AND product_code IN ({in_list});"
        )
        statements.append(sql)

    # 输出路径：默认与 Excel 同名加 _codes.sql
    if output_sql_path is None:
        output_sql_path = excel_path.with_suffix("").with_name(excel_path.stem + "_codes.sql")
    output_sql_path = Path(output_sql_path)

    with open(output_sql_path, "w", encoding="utf-8") as f:
        f.write("-- Auto-generated from Excel by generate_select_sql_from_excel\n")
        f.write(f"-- Source: {excel_path}\n")
        f.write(f"-- Total codes: {len(codes)}\n\n")
        for idx, stmt in enumerate(statements, 1):
            if len(statements) > 1:
                f.write(f"-- Part {idx}/{len(statements)}\n")
            f.write(stmt + "\n\n")

    return {
        "total_codes": len(codes),
        "statements_count": len(statements),
        "output_sql_path": str(output_sql_path),
        "preview": statements[0] if statements else "",
    }

# 示例调用
# result = generate_select_sql_from_excel(r"D:\TB\Products\barbour\document\publication\barbour_publication_xxx.xlsx")
# print(result["output_sql_path"])
# print(result["preview"])
