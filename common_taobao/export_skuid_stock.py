import os
import pandas as pd
from config import CLARKS, ECCO, GEOX
from common_taobao.txt_parser import parse_txt_to_record

BRAND_MAP = {
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def export_skuid_stock_excel(brand_name: str):
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
            for record in records:
                code, _, size, _, _, stock_status, *_ = record
                stock = 3 if stock_status == "有货" else 0
                rows.append((f"{code}_{size}", stock))
        except Exception as e:
            print(f"❌ 解析失败: {file.name} - {e}")

    if not rows:
        print("⚠️ 没有有效库存记录")
        return

    df = pd.DataFrame(rows, columns=["SKUID", "调整后库存"])
    df.to_excel(OUTPUT_DIR / "商品库存.xlsx", index=False)
    print(f"✅ 已生成: {OUTPUT_DIR / '商品库存.xlsx'}")