import os
import psycopg2
import pandas as pd
from pathlib import Path
from config import CAMPER, CLARKS_JINGYA, ECCO, GEOX,BRAND_CONFIG
# 顶部补充
import re


def _normalize_size(size: str) -> str:
    """
    统一淘宝 GEI 里的尺码格式：
    - 去掉尾部的“码”
    - 去掉前后空格
    """
    if size is None:
        return None
    s = str(size).strip()
    if s.endswith("码"):
        s = s[:-1].strip()
    return s


def _clean_id(x: object) -> str:
    """
    将 Excel 读出的 id 统一清洗成纯文本：
    - 去掉尾部的 .0
    - 处理科学计数法（如 6.083219438088E+12）
    - 去除空白
    """
    if x is None:
        return ""
    s = str(x).strip()
    # 去除常见的 .0 尾巴
    if re.fullmatch(r"\d+\.0+", s):
        return s.split(".", 1)[0]
    # 科学计数法 -> 整数串
    if re.fullmatch(r"\d+(?:\.\d+)?[eE][+-]?\d+", s):
        try:
            return str(int(float(s)))
        except Exception:
            return s
    return s

def _read_gei_as_str(gei_file: Path) -> pd.DataFrame:
    # 强制把关键列按字符串读取，避免被当作浮点
    df = pd.read_excel(
        gei_file,
        dtype={"sku名称": str, "渠道产品id": str, "货品id": str, "skuID": str}
    )
    # 统一清洗
    for col in ("sku名称", "渠道产品id", "货品id", "skuID"):
        if col in df.columns:
            df[col] = df[col].map(_clean_id)
    return df


def find_latest_gei_file(document_dir: Path) -> Path:
    files = list(document_dir.glob("GEI@sales_catalogue_export@*.xlsx"))
    if not files:
        raise FileNotFoundError("❌ 未找到 GEI@sales_catalogue_export@ 开头的文件")
    latest = max(files, key=lambda f: f.stat().st_mtime)
    print(f"📄 使用文件: {latest.name}")
    return latest

def insert_jingyaid_to_db(brand: str, debug: bool = False):
    """
    从 GEI@sales_catalogue_export@*.xlsx 更新数据库中的渠道绑定信息
    参数:
        brand: 品牌名（如 clarks_jingya）
        debug: 是否开启调试模式，若为 True，则打印跳过的编码与尺码并保存日志
    """
    import datetime

    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    config = BRAND_CONFIG[brand]
    document_dir = Path(config.get("GEI_DIR", Path(config["BASE"]) / "document"))
    output_dir = Path(config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    db_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    gei_file = find_latest_gei_file(document_dir)
    df = _read_gei_as_str(gei_file)

    updated = 0
    skipped = 0
    updated_codes: set = set()  # 去重：成功更新的商品编码
    skipped_records = []       # ⚙️ 新增：收集跳过记录
    unparsed_records = []      # ⚙️ 收集无法解析的记录

    conn = psycopg2.connect(**db_config)
    with conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                sku_name_raw = str(row.get("sku名称", "")).strip()

                # ---- 解析 sku名称 (形如 "K200155-025，40") ----
                if "，" not in sku_name_raw:
                    skipped += 1
                    unparsed_records.append({
                        "sku名称": sku_name_raw,
                        "渠道产品id": str(row.get("渠道产品id", "")),
                        "货品id": str(row.get("货品id", "")),
                        "skuID": str(row.get("skuID", "")),
                    })
                    continue

                parts = list(map(str.strip, sku_name_raw.split("，")))
                if len(parts) != 2:
                    skipped += 1
                    unparsed_records.append({
                        "sku名称": sku_name_raw,
                        "渠道产品id": str(row.get("渠道产品id", "")),
                        "货品id": str(row.get("货品id", "")),
                        "skuID": str(row.get("skuID", "")),
                    })
                    continue

                try:
                    product_code, size = parts
                    size = _normalize_size(size)
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
                        updated_codes.add(product_code)
                    else:
                        skipped += 1
                        skipped_records.append((product_code, size))

                except Exception as e:
                    print(f"❌ 行处理失败: {e}")
                    skipped += 1
                    skipped_records.append((product_code, size))

    # ---- 总结输出 ----
    print(f"✅ 更新完成：成功 {len(updated_codes)} 个商品 / {updated} 条SKU，跳过 {skipped} 条")

    # ---- 诊断：打印跳过样本，快速判断编码/尺码格式是否对不上 ----
    if skipped_records:
        print(f"⚠️ 跳过样本（前10条，格式: product_code / size）:")
        for code, size in skipped_records[:10]:
            print(f"   ⏭️  [{code}] / [{size}]")
        # 检查这些编码在数据库中是否存在（忽略尺码）
        conn2 = psycopg2.connect(**db_config)
        sample_codes = list({c for c, _ in skipped_records[:50]})
        placeholders = ",".join(["%s"] * len(sample_codes))
        with conn2.cursor() as cur2:
            cur2.execute(
                f"SELECT DISTINCT product_code FROM {table_name} WHERE product_code IN ({placeholders})",
                sample_codes,
            )
            found_in_db = {r[0] for r in cur2.fetchall()}
        conn2.close()
        not_in_db = [c for c in sample_codes if c not in found_in_db]
        if not_in_db:
            print(f"   ❌ 其中 {len(not_in_db)} 个编码在数据库中完全不存在（可能编码格式不匹配）:")
            for c in not_in_db[:10]:
                print(f"      {c}")
        else:
            print(f"   ✅ 编码在DB中均存在，问题可能出在尺码格式不匹配")

    # ---- 调试信息 ----
    if debug:
        if skipped_records:
            log_path = output_dir / f"skipped_records_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
            with open(log_path, "w", encoding="utf-8") as f:
                for code, size in skipped_records:
                    f.write(f"{code}\t{size}\n")
            print(f"🧾 已输出跳过记录文件：{log_path}")
            # 控制台打印前 20 条
            print("🔍 示例（前 20 条跳过记录）:")
            for code, size in skipped_records[:20]:
                print(f"   ⏭️ {code} / {size}")
        else:
            print("✅ 无跳过记录。")

    # ---- 无法解析的记录 ----
    if unparsed_records:
        error_df = pd.DataFrame(unparsed_records)
        error_file = output_dir / "unparsed_sku_names.xlsx"
        error_df.to_excel(error_file, index=False)
        print(f"⚠️ 无法解析的记录已输出到：{error_file}")
    else:
        print("✅ 没有无法解析的记录")


def insert_missing_products_with_zero_stock(brand: str):
    """
    从 GEI@sales_catalogue_export@*.xlsx 补齐数据库：
    - 对缺失的 (product_code, size) 插入新行（stock_count=0），并写入 skuid / channel_product_id / channel_item_id / sku_name；
    - 对已存在但 skuid 为空的行进行 UPDATE 补齐；
    - 仅以 GEI 里实际出现过的尺码为准，不再根据标题猜尺码。
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    config = BRAND_CONFIG[brand]
    document_dir = Path(config.get("GEI_DIR", Path(config["BASE"]) / "document"))
    output_dir = Path(config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    db_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    gei_file = find_latest_gei_file(document_dir)
    df = _read_gei_as_str(gei_file)

    # —— 1) 解析 GEI：构建 (product_code, size) → info 映射（含 skuid）
    # GEI 列名示例：sku名称（形如 "K200155-025，40"），渠道产品id，货品id，skuID
    sku_map = {}  # key: (code, size) -> dict(...)
    unparsed_rows = []

    for _, row in df.iterrows():
        sku_name_raw = str(row.get("sku名称", "")).strip()
        if "，" not in sku_name_raw:
            unparsed_rows.append({
                "sku名称": sku_name_raw,
                "渠道产品id": str(row.get("渠道产品id", "")),
                "货品id": str(row.get("货品id", "")),
                "skuID": str(row.get("skuID", "")),
            })
            continue

        parts = [p.strip() for p in sku_name_raw.split("，")]
        if len(parts) != 2:
            unparsed_rows.append({
                "sku名称": sku_name_raw,
                "渠道产品id": str(row.get("渠道产品id", "")),
                "货品id": str(row.get("货品id", "")),
                "skuID": str(row.get("skuID", "")),
            })
            continue

        code, size = parts
        size = _normalize_size(size)   # ⭐⭐新增同样的清洗步骤
        skuid              = _clean_id(row.get("skuID", ""))   # ← 关键
        channel_product_id = _clean_id(row.get("渠道产品id", ""))
        channel_item_id    = _clean_id(row.get("货品id", ""))
        # 你的 insert_jingyaid_to_db 里这样构造 sku_name：
        sku_name = code.replace("-", "") + size

        sku_map[(code, size)] = {
            "product_code": code,
            "size": size,
            "skuid": skuid,
            "channel_product_id": channel_product_id,
            "channel_item_id": channel_item_id,
            "sku_name": sku_name,
        }

    print(f"🧩 解析 GEI 完成：有效 (code,size) = {len(sku_map)}")

    if unparsed_rows:
        pd.DataFrame(unparsed_rows).to_excel(output_dir / "unparsed_sku_names.xlsx", index=False)
        print(f"⚠️ 无法解析的 GEI 行已输出：{output_dir / 'unparsed_sku_names.xlsx'}")

    # —— 2) 查询数据库已存在的 (product_code, size)
    conn = psycopg2.connect(**db_config)
    existing_keys = set()
    with conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT product_code, size, COALESCE(NULLIF(TRIM(skuid), ''), NULL) AS skuid FROM {table_name}")
            rows = cur.fetchall()
            # rows: list of tuples (code, size, skuid_or_none)
            existing_with_skuid = set()
            existing_without_skuid = set()
            for code, size, sk in rows:
                key = (str(code), str(size))
                existing_keys.add(key)
                if sk:
                    existing_with_skuid.add(key)
                else:
                    existing_without_skuid.add(key)

    # —— 3) 需要插入的缺失键（只以 GEI 中有的数据为准）
    to_insert = [k for k in sku_map.keys() if k not in existing_keys]
    # —— 4) 需要更新 skuid 的键（库里有该行但 skuid 为空，且 GEI 有 skuid）
    to_update = [k for k in existing_without_skuid if k in sku_map and sku_map[k]["skuid"]]

    print(f"➕ 待插入: {len(to_insert)} 行；🛠 待补齐 skuid: {len(to_update)} 行")

    inserted = 0
    updated = 0

    with conn:
        with conn.cursor() as cur:
            # 3) 插入缺失行（stock_count=0；带 skuid / channel_* / sku_name）
            insert_sql = f"""
                INSERT INTO {table_name} (
                    product_code, product_url, size, gender,
                    stock_count, channel_product_id, channel_item_id,
                    skuid, sku_name,
                    is_published, last_checked
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
            """
            # 性别无法从 GEI 精准判断，这里不再猜；统一 None 或留空
            for key in to_insert:
                info = sku_map[key]
                cur.execute(insert_sql, (
                    info["product_code"],
                    "",                  # product_url 占位
                    info["size"],
                    None,                # gender 不再猜
                    0,                   # stock_count = 0
                    info["channel_product_id"],
                    info["channel_item_id"],
                    info["skuid"],
                    info["sku_name"],
                ))
                inserted += 1

            # 4) 更新已有但 skuid 为空的行（同时补齐 sku_name 与 channel_*）
            update_sql = f"""
                UPDATE {table_name}
                SET skuid = %s,
                    sku_name = %s,
                    channel_product_id = COALESCE(NULLIF(%s, ''), channel_product_id),
                    channel_item_id = COALESCE(NULLIF(%s, ''), channel_item_id),
                    last_checked = CURRENT_TIMESTAMP
                WHERE product_code = %s AND size = %s AND (skuid IS NULL OR TRIM(skuid) = '')
            """
            for key in to_update:
                info = sku_map[key]
                cur.execute(update_sql, (
                    info["skuid"],
                    info["sku_name"],
                    info["channel_product_id"],
                    info["channel_item_id"],
                    info["product_code"],
                    info["size"],
                ))
                updated += cur.rowcount

    conn.close()
    print(f"✅ 插入完成：新增 {inserted} 行；✅ 补齐 skuid：更新 {updated} 行")






if __name__ == "__main__":
    #insert_jingyaid_to_db("camper")
    insert_missing_products_with_zero_stock("camper")