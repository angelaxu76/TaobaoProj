import re
import pandas as pd
from pathlib import Path
from config import BRAND_CONFIG


def extract_product_codes_from_txt(txt_path: Path) -> list[str]:
    """
    从商品链接 TXT 中提取商品编码（如 K300453-011），返回去重排序后的编码列表。
    """
    code_pattern = re.compile(r"[A-Z]?\d{5,6}-\d{3}")
    codes = set()

    if not txt_path.exists():
        raise FileNotFoundError(f"❌ 文件不存在: {txt_path}")

    with txt_path.open("r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            match = code_pattern.search(url)
            if match:
                codes.add(match.group(0))

    return sorted(codes)


def find_item_ids_for_product_codes(brand: str):
    """
    提取链接中的商品编码 → 在店铺 Excel 中查找 item_id → 输出 Excel。
    参数:
        brand: 品牌名（如 camper）
    输出:
        document/camper_encoded_itemids.xlsx
    """
    brand = brand.lower()
    config = BRAND_CONFIG[brand]
    txt_path = Path(config["TXT_DIR"]).parent / "product_links.txt"
    output_path = Path(config["BASE"]) / "document" / f"{brand}_encoded_itemids.xlsx"
    store_dir = Path(config["STORE_DIR"])

    print("🟡 Step 1️⃣ 提取商品编码...")
    product_codes = extract_product_codes_from_txt(txt_path)
    print(f"✅ 提取 {len(product_codes)} 个商品编码")

    print("🟡 Step 2️⃣ 查找宝贝ID并导出...")
    output_rows = []

    for store_excel in store_dir.glob("*.xls*"):
        if store_excel.name.startswith("~$"):
            continue
        print(f"📂 读取文件: {store_excel.name}")
        df = pd.read_excel(store_excel, dtype=str).fillna(method="ffill")

        for _, row in df.iterrows():
            code = str(row.get("商家编码", "")).strip()
            item_id = str(row.get("宝贝ID", "")).strip()
            if code in product_codes and item_id:
                output_rows.append({
                    "商品编码": code,
                    "淘宝宝贝ID": item_id,
                    "店铺": store_excel.stem
                })

    if output_rows:
        pd.DataFrame(output_rows).drop_duplicates().to_excel(output_path, index=False)
        print(f"✅ 匹配到 {len(output_rows)} 条记录，已导出: {output_path}")
    else:
        print("⚠️ 未找到任何匹配的编码")
