
import pandas as pd

# === 🛠 Excel 输入路径配置（请根据实际路径修改） ===
EXCEL_FILE = r"D:\TB\sycm\【生意参谋平台】商品_全部_2025-06-07_2025-07-06.xlsx"

def get_filtered_products_by_brand(filepath=EXCEL_FILE):
    """
    从生意参谋 Excel 文件中读取数据，并返回按品牌分类的满足条件的商品列表。
    返回：
        - brand_product_map: dict[str, list[tuple[str, str]]]
        - df_filtered: DataFrame 含品牌、商品ID、主商品ID
    """
    df = pd.read_excel(filepath)
    df.columns = df.iloc[3]   # 第4行为表头
    df = df[4:].reset_index(drop=True)

    # 清洗并转换数值字段
    df["支付件数"] = pd.to_numeric(df["支付件数"].astype(str).str.replace(",", ""), errors="coerce")
    df["商品收藏人数"] = pd.to_numeric(df["商品收藏人数"].astype(str).str.replace(",", ""), errors="coerce")
    df["商品加购人数"] = pd.to_numeric(df["商品加购人数"].astype(str).str.replace(",", ""), errors="coerce")

    # 筛选满足任一条件的商品
    df_filtered = df[
        (df["支付件数"] >= 2) |
        (df["商品收藏人数"] > 5) |
        (df["商品加购人数"] > 5)
    ].copy()

    # 品牌关键词列表（优先匹配顺序）
    brands = ["ecco", "clarks", "geox", "camper", "birkenstock", "reiss", "barbour"]

    # 提取品牌字段
    def identify_brand(name: str):
        name = str(name).lower()
        for brand in brands:
            if brand in name:
                return brand
        return "其他"

    df_filtered["品牌"] = df_filtered["商品名称"].astype(str).apply(identify_brand)

    # 输出按品牌分组的字典
    brand_product_map = {}
    for brand in brands:
        subset = df_filtered[df_filtered["品牌"] == brand]
        brand_product_map[brand] = list(zip(subset["商品ID"], subset["主商品ID"]))

    return brand_product_map, df_filtered[["品牌", "商品ID", "主商品ID"]]


# === 示例执行 ===
if __name__ == "__main__":
    brand_map, df_info = get_filtered_products_by_brand()
    print("可识别品牌：", list(brand_map.keys()))
    for brand, items in brand_map.items():
        print(f"[{brand}] 商品数量: {len(items)}")
