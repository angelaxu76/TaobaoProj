import os
import pandas as pd
from config import CLARKS, ECCO, GEOX
from common_taobao.txt_parser import parse_txt_to_record

BRAND_MAP = {
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def export_discount_price_excel(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
    TXT_DIR = config["TXT_DIR"]
    OUTPUT_DIR = config["OUTPUT_DIR"]

    rows = []
    for file in TXT_DIR.glob("*.txt"):
        try:
            records = parse_txt_to_record(file)
            if not records:
                print(f"⚠️ 无有效价格: {file.name}")
                continue
            code = records[0][0]  # product_code
            discount = records[0][7]  # discount_price
            rows.append((code, discount))
        except Exception as e:
            print(f"❌ 解析失败: {file.name} - {e}")

    if not rows:
        print("⚠️ 没有任何有效数据导出")
        return

    df = pd.DataFrame(rows, columns=["商家编码", "优惠后价"])
    df.to_excel(OUTPUT_DIR / "商品价格.xlsx", index=False)
    print(f"✅ 已生成: {OUTPUT_DIR / '商品价格.xlsx'}")