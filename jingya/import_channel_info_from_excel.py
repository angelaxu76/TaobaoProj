import os
import psycopg2
import pandas as pd
from pathlib import Path
from config import CAMPER, CLARKS, ECCO, GEOX

BRAND_MAP = {
    "camper": CAMPER,
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def find_latest_gei_file(document_dir: Path) -> Path:
    files = list(document_dir.glob("GEI@sales_catalogue_export@*.xlsx"))
    if not files:
        raise FileNotFoundError("❌ 未找到 GEI@sales_catalogue_export@ 开头的文件")
    latest = max(files, key=lambda f: f.stat().st_mtime)
    print(f"📄 使用文件: {latest.name}")
    return latest

def parse_and_update_excel(brand: str):
    brand = brand.lower()
    if brand not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    config = BRAND_MAP[brand]
    document_dir = Path(config["BASE"]) / "document"
    db_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    gei_file = find_latest_gei_file(document_dir)
    df = pd.read_excel(gei_file)

    updated = 0
    skipped = 0

    conn = psycopg2.connect(**db_config)
    with conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                sku_name_raw = str(row.get("sku名称", ""))
                if "，" not in sku_name_raw:
                    skipped += 1
                    continue

                parts = list(map(str.strip, sku_name_raw.split("，")))
                if len(parts) != 2:
                    print(f"⚠️ 无法解析 sku名称: {sku_name_raw}")
                    skipped += 1
                    continue

                try:
                    product_code, size = parts
                    new_sku_name = product_code.replace("-", "") + size
                    sql = f"""
                        UPDATE {table_name}
                        SET
                            channel_product_id = %s,
                            channel_item_id = %s,
                            skuid = %s,
                            sku_name = %s,
                            is_published = TRUE,
                            last_checked = CURRENT_TIMESTAMP
                        WHERE product_code = %s AND size = %s
                    """
                    params = (
                        str(row.get("渠道产品id")),
                        str(row.get("货品id")),
                        str(row.get("skuID")),
                        new_sku_name,
                        product_code,
                        size
                    )
                    cur.execute(sql, params)
                    if cur.rowcount:
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    print(f"❌ 行处理失败: {e}")
                    skipped += 1

    print(f"✅ 更新完成：成功 {updated} 条，跳过 {skipped} 条")

if __name__ == "__main__":
    parse_and_update_excel("camper")