import os
import psycopg2
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import CLARKS, ECCO, GEOX, CAMPER, BRAND_CONFIG
from common_taobao.txt_parser import parse_txt_to_record
from common_taobao.core.price_utils import calculate_discount_price_from_float

# —— 品牌折扣（对 base_price 先打折；1.0=不打折）——
BRAND_BASE_DISCOUNT = {
    "ecco":   0.9,   # 例如 ECCO 不折
    "clarks": 1,   # 例如 Clarks 85 折
    "camper": 0.75,
    "geox":   0.9,
    # 其他品牌按需补充
}
def get_brand_discount(brand: str) -> float:
    try:
        d = float(BRAND_BASE_DISCOUNT.get(brand.lower(), 1.0))
        # 护栏：防止传入 0 或异常值
        return 1.0 if d <= 0 else d
    except Exception:
        return 1.0


def load_sku_mapping_from_store(store_path: Path):
    sku_map = {}
    for file in store_path.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        print(f"📂 读取映射文件: {file.name}")
        df = pd.read_excel(file, dtype=str)
        df = df.fillna(method="ffill")  # 修复合并单元格中缺失的宝贝ID、商家编码
        for _, row in df.iterrows():
            spec = str(row.get("sku规格", "")).replace("，", ",").strip().rstrip(",")
            skuid = str(row.get("skuID", "")).strip()
            itemid = str(row.get("宝贝ID", "")).strip()
            if spec and skuid:
                sku_map[spec] = (skuid, itemid if itemid else None)
    return sku_map


def import_txt_to_db(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_CONFIG[brand_name]
    TXT_DIR = config["TXT_DIR"]
    PGSQL = config["PGSQL_CONFIG"]
    TABLE_NAME = config["TABLE_NAME"]
    STORE_DIR = config["STORE_DIR"]

    conn = psycopg2.connect(**PGSQL)
    cur = conn.cursor()

    if brand_name == "camper":
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                product_code, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                taobao_store_price,
                stock_name, last_checked, is_published, ean, item_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_code, size, stock_name)
            DO UPDATE SET
                stock_status = EXCLUDED.stock_status,
                discount_price_gbp = EXCLUDED.discount_price_gbp,
                original_price_gbp = EXCLUDED.original_price_gbp,
                taobao_store_price = EXCLUDED.taobao_store_price,
                skuid = EXCLUDED.skuid,
                item_id = EXCLUDED.item_id,
                last_checked = EXCLUDED.last_checked,
                is_published = EXCLUDED.is_published,
                ean = EXCLUDED.ean;
        """
    else:
        # （示例）非 camper 分支：多了 taobao_store_price
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                product_code, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                taobao_store_price,
                stock_name, last_checked, is_published, item_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_code, size, stock_name)
            DO UPDATE SET
                stock_status = EXCLUDED.stock_status,
                discount_price_gbp = EXCLUDED.discount_price_gbp,
                original_price_gbp = EXCLUDED.original_price_gbp,
                taobao_store_price = EXCLUDED.taobao_store_price,
                skuid = EXCLUDED.skuid,
                item_id = EXCLUDED.item_id,
                last_checked = EXCLUDED.last_checked,
                is_published = EXCLUDED.is_published;
        """


    txt_files = list(TXT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"⚠️ 没有 TXT 文件在目录 {TXT_DIR}")
        return

    for store_folder in STORE_DIR.iterdir():
        if not store_folder.is_dir() or store_folder.name == "clarks_default":
            continue
        stock_name = store_folder.name
        print(f"🔄 处理店铺: {stock_name}")

        sku_map = load_sku_mapping_from_store(store_folder)
        print(f"🔢 映射表共 {len(sku_map)} 条")

        for file in txt_files:
            try:
                records = parse_txt_to_record(file, brand_name)
                if not records:
                    print(f"⚠️ 无数据: {file.name}")
                    continue

                inserted = 0
                for r in records:
                    if brand_name == "camper":
                        product_code, url, size, gender, _, stock_status, ori_price, dis_price, _, ean = r
                    else:
                        product_code, url, size, gender, _, stock_status, ori_price, dis_price, _ = r
                        ean = None

                    # 清洗价格字段
                    ori_price = float(ori_price) if isinstance(ori_price, (int,float,str)) and str(ori_price).replace('.', '', 1).isdigit() else None
                    dis_price = float(dis_price) if isinstance(dis_price, (int,float,str)) and str(dis_price).replace('.', '', 1).isdigit() else None

                    # 取非零最小值作为 base_price（排除 0 / None）
                    candidates = [p for p in (ori_price, dis_price) if p is not None and p > 0]
                    base_price = min(candidates) if candidates else None

                    # —— 按品牌对 base_price 先打折 ——
                    brand_discount = get_brand_discount(brand_name)
                    discounted_base = None
                    if base_price is not None:
                        discounted_base = base_price * brand_discount

                    # 计算导入价（人民币）：用折后价参与 price_utils 规则
                    store_price = None
                    if discounted_base is not None and discounted_base > 0:
                        store_price = float(calculate_discount_price_from_float(discounted_base))
                    else:
                        store_price = None  # 禁止用 0 价/空价参与计算，避免假价污染

                    # 统一打印一行调试信息
                    print(f"[DEBUG] brand={brand_name}, discount={brand_discount}, "
                        f"ori_price={ori_price}, dis_price={dis_price}, "
                        f"base_price={base_price}, discounted_base={discounted_base}, store_price={store_price}, "
                        f"product_code={product_code}, size={size}, stock_name={stock_name}")



                    spec_key = f"{product_code},{size}"
                    sku_entry = sku_map.get(spec_key)

                    if sku_entry:
                        skuid, item_id = sku_entry
                        if not item_id and skuid:
                            item_id = next((iid for sid, iid in sku_map.values() if sid == skuid and iid), None)
                        print(f"🔑 匹配成功: {spec_key} → SKU ID: {skuid}, 宝贝ID: {item_id}")
                    else:
                        skuid = item_id = None
                        print(f"⚠️ 未匹配 SKU: {spec_key}")

                    is_published = skuid is not None

                    full_record = (
                        product_code, url, size, gender, skuid,
                        stock_status, ori_price, dis_price,
                        store_price,                    # 👈 新增：taobao_store_price
                        stock_name, datetime.now(), is_published, item_id
                    )

                    if brand_name == "camper":
                        # camper: 有 ean，且现在也有 taobao_store_price（见上面的 insert_sql）
                        full_record = (
                            product_code, url, size, gender, skuid,
                            stock_status, ori_price, dis_price,
                            store_price,
                            stock_name, datetime.now(), is_published, ean, item_id
                        )
                    else:
                        # 其它品牌
                        full_record = (
                            product_code, url, size, gender, skuid,
                            stock_status, ori_price, dis_price,
                            store_price,
                            stock_name, datetime.now(), is_published, item_id
                        )

                    try:
                        cur.execute(insert_sql, full_record)
                        inserted += 1
                    except Exception as e:
                        conn.rollback()
                        print(f"❌ 插入失败: {file.name} - {e}")

                print(f"✅ 已导入: {file.name}（{inserted} 条） → 店铺: {stock_name}")
            except Exception as e:
                print(f"❌ 错误文件: {file.name} - {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ 品牌 [{brand_name}] 的 TXT 数据已全部导入数据库。")
