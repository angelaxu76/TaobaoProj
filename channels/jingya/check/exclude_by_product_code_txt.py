import pandas as pd


def exclude_excel_rows_by_txt(
    excel_path: str,
    txt_path: str,
    output_path: str,
    product_code_cols=None,
):
    """
    从 Excel 中删除：商品编码存在于 TXT 中的行
    支持多个商品编码列名，自动匹配第一个存在的
    """

    if product_code_cols is None:
        product_code_cols = [
            "product_code",
            "Product Code",
            "商品编码",
            "商家编码",
            "SKUID",
            "Item ID",
            "item_id",
        ]

    # ========= 1. 读取 TXT =========
    with open(txt_path, "r", encoding="utf-8") as f:
        exclude_codes = {line.strip() for line in f if line.strip()}

    print(f"📄 TXT 中读取到 {len(exclude_codes)} 个商品编码")

    # ========= 2. 读取 Excel =========
    df = pd.read_excel(excel_path)

    # ========= 3. 自动识别编码列 =========
    product_code_col = None
    for col in product_code_cols:
        if col in df.columns:
            product_code_col = col
            break

    if product_code_col is None:
        raise KeyError(
            f"❌ Excel 中未找到商品编码列，尝试过的列名：{product_code_cols}\n"
            f"📋 实际列名：{list(df.columns)}"
        )

    print(f"✅ 使用商品编码列：{product_code_col}")

    total_before = len(df)

    # ========= 4. 排除 =========
    df_filtered = df[
        ~df[product_code_col].astype(str).isin(exclude_codes)
    ].copy()

    total_after = len(df_filtered)

    # ========= 5. 导出 =========
    df_filtered.to_excel(output_path, index=False)

    print("✅ 排除完成")
    print(f"📊 原始行数: {total_before}")
    print(f"📊 排除后行数: {total_after}")
    print(f"📊 共排除: {total_before - total_after}")
    print(f"📁 输出文件: {output_path}")
