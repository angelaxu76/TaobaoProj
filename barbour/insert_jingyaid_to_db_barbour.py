# -*- coding: utf-8 -*-
import os
import re
import psycopg2
import pandas as pd
from pathlib import Path
from config import BRAND_CONFIG  # 请在 BRAND_CONFIG 里添加 barbour 配置：TABLE_NAME/PGSQL_CONFIG/BASE 等

# 复用你现有的“最新 GEI 文件查找”思路（文件名形如 GEI@sales_catalogue_export@*.xlsx）
def find_latest_gei_file(document_dir: Path) -> Path:
    files = list(document_dir.glob("GEI@sales_catalogue_export@*.xlsx"))
    if not files:
        raise FileNotFoundError("❌ 未找到 GEI@sales_catalogue_export@*.xlsx")
    latest = max(files, key=lambda f: f.stat().st_mtime)
    print(f"📄 使用文件: {latest.name}")
    return latest

def _split_sku_name(s: str):
    """
    兼容 '，' 与 ','；容忍空格。期待形如：MWX0339NY91，M  或  MWX0339NY91, M
    返回 (product_code, size)，不做大小写变换。
    """
    if not s:
        return None
    s = str(s).strip()
    # 统一替换为中文逗号，再按中文逗号切
    s = s.replace(",", "，")
    parts = [p.strip() for p in s.split("，") if p.strip()]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]

def insert_jingyaid_to_db(brand: str):
    """
    将鲸芽 Excel 的 channel_product_id / channel_item_id / skuID 绑定信息
    写入 {TABLE_NAME}（这里表是 barbour_inventory），并 is_published=True。
    逻辑与 clarks_jingya 版本一致，仅解析规则更宽松。
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    cfg = BRAND_CONFIG[brand]
    table_name = cfg["TABLE_NAME"]                  # 需配置为 'barbour_inventory'
    db_conf    = cfg["PGSQL_CONFIG"]
    doc_dir    = Path(cfg["BASE"]) / "document"
    out_dir    = Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)

    gei_file = find_latest_gei_file(doc_dir)
    df = pd.read_excel(gei_file)

    updated, skipped = 0, 0
    unparsed = []

    conn = psycopg2.connect(**db_conf)
    with conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                sku_name_raw = str(row.get("sku名称", "")).strip()
                parsed = _split_sku_name(sku_name_raw)
                if not parsed:
                    skipped += 1
                    unparsed.append({
                        "sku名称": sku_name_raw,
                        "渠道产品id": str(row.get("渠道产品id", "")),
                        "货品id": str(row.get("货品id", "")),
                        "skuID": str(row.get("skuID", "")),
                    })
                    continue

                product_code, size = parsed  # Barbour 的 color_code + 尺码（如 M/L/XL 或 UK 36）

                # sku_name 生成策略：直接拼接，和你现有风格一致（可按需改）
                new_sku_name = f"{product_code}{size}"

                sql = f"""
                    UPDATE {table_name}
                    SET channel_product_id = %s,
                        channel_item_id    = %s,
                        skuid              = %s,
                        sku_name           = %s,
                        is_published       = TRUE,
                        last_checked       = CURRENT_TIMESTAMP
                    WHERE product_code = %s AND size = %s
                """
                params = (
                    str(row.get("渠道产品id", "")),
                    str(row.get("货品id", "")),
                    str(row.get("skuID", "")),
                    new_sku_name,
                    product_code,
                    size,
                )
                cur.execute(sql, params)
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1

    print(f"✅ 绑定更新完成：成功 {updated} 条，未匹配 {skipped} 条")
    if unparsed:
        pd.DataFrame(unparsed).to_excel(out_dir / "unparsed_sku_names_barbour.xlsx", index=False)
        print(f"⚠️ 无法解析的记录已输出到：{out_dir / 'unparsed_sku_names_barbour.xlsx'}")

def insert_missing_products_with_zero_stock(brand: str):
    """
    若 Excel 中存在某些 product_code（color_code），但库内缺失，
    按尺码批量插入占位 SKU（stock_count=0），以便后续清零/回写覆盖淘宝历史遗留。
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    cfg = BRAND_CONFIG[brand]
    table_name = cfg["TABLE_NAME"]
    db_conf    = cfg["PGSQL_CONFIG"]
    doc_dir    = Path(cfg["BASE"]) / "document"
    out_dir    = Path(cfg["OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    missing_file = out_dir / "missing_product_codes_barbour.txt"

    gei_file = find_latest_gei_file(doc_dir)
    df = pd.read_excel(gei_file)

    # Excel → product_code 基础映射
    product_info = {}
    for _, row in df.iterrows():
        parsed = _split_sku_name(str(row.get("sku名称", "")))
        if parsed:
            code, _ = parsed
            product_info.setdefault(code, {
                "channel_product_id": str(row.get("渠道产品id", "")).strip(),
                "channel_item_id":    str(row.get("货品id", "")).strip(),
            })

    conn = psycopg2.connect(**db_conf)
    with conn:
        with conn.cursor() as cur:
            excel_codes = set(product_info.keys())
            cur.execute(f"SELECT DISTINCT product_code FROM {table_name}")
            db_codes = {r[0] for r in cur.fetchall()}

            missing = sorted(excel_codes - db_codes)
            with open(missing_file, "w", encoding="utf-8") as f:
                for code in missing:
                    f.write(code + "\n")
            print(f"🔍 缺失商品编码：{len(missing)}，已写入 {missing_file}")

            # Barbour 尺码：先保守用 S/M/L/XL（可按你库里的实际尺码表替换）
            default_sizes = ["XS","S","M","L","XL","XXL"]

            inserted = 0
            for code in missing:
                chp = product_info.get(code, {}).get("channel_product_id", "")
                chi = product_info.get(code, {}).get("channel_item_id", "")
                for size in default_sizes:
                    cur.execute(
                        f"""INSERT INTO {table_name} (
                                product_code, product_url, size, gender,
                                stock_count, channel_product_id, channel_item_id,
                                is_published, last_checked
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,CURRENT_TIMESTAMP)
                            ON CONFLICT (product_code,size) DO NOTHING
                        """,
                        (code, "", size, None, 0, chp, chi)
                    )
                    inserted += cur.rowcount
            print(f"✅ 占位插入完成：新增 {inserted} 条")
