import os
import psycopg2
import pandas as pd
from pathlib import Path
from config import CAMPER, CLARKS, ECCO, GEOX,BRAND_CONFIG


def find_latest_gei_file(document_dir: Path) -> Path:
    files = list(document_dir.glob("GEI@sales_catalogue_export@*.xlsx"))
    if not files:
        raise FileNotFoundError("❌ 未找到 GEI@sales_catalogue_export@ 开头的文件")
    latest = max(files, key=lambda f: f.stat().st_mtime)
    print(f"📄 使用文件: {latest.name}")
    return latest

def insert_jingyaid_to_db(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    config = BRAND_CONFIG[brand]
    document_dir = Path(config["BASE"]) / "document"
    output_dir = Path(config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    db_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    gei_file = find_latest_gei_file(document_dir)
    df = pd.read_excel(gei_file)

    updated = 0
    skipped = 0

    # ✅ 用于收集解析失败的记录
    unparsed_records = []

    conn = psycopg2.connect(**db_config)
    with conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                sku_name_raw = str(row.get("sku名称", "")).strip()

                if "，" not in sku_name_raw:
                    skipped += 1
                    # ✅ 收集无法解析的记录
                    unparsed_records.append({
                        "sku名称": sku_name_raw,
                        "渠道产品id": str(row.get("渠道产品id", "")),
                        "货品id": str(row.get("货品id", "")),
                        "skuID": str(row.get("skuID", ""))
                    })
                    continue

                parts = list(map(str.strip, sku_name_raw.split("，")))
                if len(parts) != 2:
                    skipped += 1
                    # ✅ 收集无法解析的记录
                    unparsed_records.append({
                        "sku名称": sku_name_raw,
                        "渠道产品id": str(row.get("渠道产品id", "")),
                        "货品id": str(row.get("货品id", "")),
                        "skuID": str(row.get("skuID", ""))
                    })
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

    # ✅ 将无法解析的记录输出到 Excel
    if unparsed_records:
        error_df = pd.DataFrame(unparsed_records)
        error_file = output_dir / "unparsed_sku_names.xlsx"
        error_df.to_excel(error_file, index=False)
        print(f"⚠️ 无法解析的记录已输出到：{error_file}")
    else:
        print("✅ 没有无法解析的记录")

def insert_missing_products_with_zero_stock(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    config = BRAND_CONFIG[brand]
    document_dir = Path(config["BASE"]) / "document"
    output_dir = Path(config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    missing_file = output_dir / "missing_product_codes.txt"

    db_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    gei_file = find_latest_gei_file(document_dir)
    df = pd.read_excel(gei_file)

    # ✅ 创建映射表：product_code -> (title, channel_product_id, channel_item_id)
    product_info_map = {}
    for _, row in df.iterrows():
        sku_name_raw = str(row.get("sku名称", ""))
        if "，" in sku_name_raw:
            code = sku_name_raw.split("，")[0].strip()
            product_info_map[code] = {
                "title": str(row.get("渠道产品名称", "")),
                "channel_product_id": str(row.get("渠道产品id", "")).strip(),
                "channel_item_id": str(row.get("货品id", "")).strip()
            }

    inserted = 0

    conn = psycopg2.connect(**db_config)
    with conn:
        with conn.cursor() as cur:
            # 1. 从 Excel 提取所有 product_code
            excel_product_codes = set(product_info_map.keys())

            # 2. 查询数据库已有的 product_code
            cur.execute(f"SELECT DISTINCT product_code FROM {table_name}")
            db_product_codes = set([r[0] for r in cur.fetchall()])

            # 3. 找出缺失的 product_code
            missing_codes = excel_product_codes - db_product_codes
            print(f"🔍 缺失商品编码数量: {len(missing_codes)}")

            # 4. 输出缺失商品编码到 TXT 文件
            with open(missing_file, "w", encoding="utf-8") as f:
                for code in sorted(missing_codes):
                    f.write(code + "\n")
            print(f"✅ 缺失商品编码已写入文件：{missing_file}")

            # 5. 插入缺失商品（带 channel_product_id 和 channel_item_id）
            for code in missing_codes:
                info = product_info_map.get(code, {})
                title = info.get("title", "")
                channel_product_id = info.get("channel_product_id", "")
                channel_item_id = info.get("channel_item_id", "")

                # 根据标题推断性别并设置尺码
                if "男" in title:
                    gender = "男款"
                    sizes = ["39", "40", "41", "42", "43", "44", "45", "46"]
                elif "女" in title:
                    gender = "女款"
                    sizes = ["35", "36", "37", "38", "39", "40", "41", "42"]
                else:
                    gender = "男款"
                    sizes = ["39", "40", "41", "42", "43", "44", "45", "46"]

                for size in sizes:
                    insert_sql = f"""
                        INSERT INTO {table_name} (
                            product_code, product_url, size, gender,
                            stock_count, channel_product_id, channel_item_id,
                            is_published, last_checked
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
                    """
                    cur.execute(insert_sql, (
                        code, "", size, gender, 0,
                        channel_product_id, channel_item_id
                    ))
                    inserted += 1

    print(f"✅ 插入完成：新增 {inserted} 条（缺失商品共 {len(missing_codes)} 个）")
    print(f"📂 TXT 文件位置: {missing_file}")





if __name__ == "__main__":
    #insert_jingyaid_to_db("camper")
    insert_missing_products_with_zero_stock("camper")