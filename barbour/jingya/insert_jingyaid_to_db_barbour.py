# -*- coding: utf-8 -*-
"""
Barbour 渠道绑定（保持原方法名，不破坏旧脚本）：
1) insert_missing_products_with_zero_stock(brand):
   - 从 GEI@sales_catalogue_export@*.xlsx 读取 sku名称，抽取 (product_code, size)
   - 若 DB 中缺少该 product_code（或缺少对应 size），插入占位记录 stock_count=0
   - 用 Excel 中的渠道信息（若有）写入 channel_product_id/channel_item_id

2) insert_jingyaid_to_db(brand):
   - 将 Excel 的三列原样写入：
       skuid    <- skuID
       sku_name <- sku名称
       item_id  <- 货品id
   - WHERE 条件：sku名称 拆成 (product_code, size)
   - 若 Excel 同时含有 “渠道产品id / channel_item_id”，也一并更新（可缺省）

主程序默认顺序：先占位 -> 再绑定。
"""
import sys
import re
from pathlib import Path
import pandas as pd
import psycopg2
from config import BRAND_CONFIG  # 需配置 BRAND_CONFIG["barbour"]:{TABLE_NAME,PGSQL_CONFIG,BASE,OUTPUT_DIR}

# ========= 公用工具 =========
def find_latest_gei_file(document_dir: Path) -> Path:
    files = list(document_dir.glob("GEI@sales_catalogue_export@*.xlsx"))
    if not files:
        raise FileNotFoundError("未找到 GEI@sales_catalogue_export@*.xlsx")
    return max(files, key=lambda f: f.stat().st_mtime)

def normalize_col(col: str) -> str:
    """列名归一：去空格、全角转半角、去尾部标点，统一为小写"""
    s = (str(col) or "").strip()
    # 全角->半角
    def q2b(t):
        out = []
        for ch in t:
            code = ord(ch)
            if code == 12288:
                code = 32
            elif 65281 <= code <= 65374:
                code -= 65248
            out.append(chr(code))
        return "".join(out)
    s = q2b(s)
    s = re.sub(r"[，,。.\s]+$", "", s)  # 去末尾逗号/句号/空白
    return s.lower()

def split_sku_name(s: str):
    """最小分隔：支持 '，' 或 ','；返回 (product_code, size) 或 None"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.replace(",", "，")
    parts = [p.strip() for p in s.split("，") if p.strip()]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]

def clear_barbour_inventory():
    """清空 Barbour inventory 表（用于全量初始化）"""
    import psycopg2
    from config import BRAND_CONFIG
    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

    sql = """
    TRUNCATE TABLE barbour_inventory RESTART IDENTITY;
    """
    conn = psycopg2.connect(**cfg)
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("🧹 已清空 barbour_inventory 表。")


def _load_excel_with_colmap(gei_path: Path):
    df = pd.read_excel(gei_path)
    colmap = {normalize_col(c): c for c in df.columns}

    # 关键列（容错匹配）
    key_sku_id   = next((colmap[k] for k in colmap if k in ("skuid", "sku id", "sku_id")), None)
    key_sku_name = next((colmap[k] for k in colmap if k in ("sku名称", "sku name", "skuname", "sku 名称", "sku名稱")), None)
    key_item_id  = next((colmap[k] for k in colmap if k in ("货品id", "item id", "item_id", "貨品id")), None)

    # 选配（可能没有）
    key_ch_prod  = next((colmap[k] for k in colmap if k in ("渠道产品id", "channel_product_id", "渠道產品id")), None)
    key_ch_item  = next((colmap[k] for k in colmap if k in ("channel_item_id", "渠道itemid", "渠道item_id")), None)

    if not key_sku_name:
        raise RuntimeError("Excel 缺少必须列：sku名称")
    return df, key_sku_id, key_sku_name, key_item_id, key_ch_prod, key_ch_item

# ========= 方法 1：占位插入 =========
def insert_missing_products_with_zero_stock(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise RuntimeError(f"BRAND_CONFIG 未配置 {brand}")

    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]          # 'barbour_inventory'
    db    = cfg["PGSQL_CONFIG"]
    doc   = Path(cfg["BASE"]) / "document"
    out   = Path(cfg["OUTPUT_DIR"]); out.mkdir(parents=True, exist_ok=True)

    gei = find_latest_gei_file(doc)
    print(f"[占位] 使用文件：{gei}")
    df, key_sku_id, key_sku_name, key_item_id, key_ch_prod, key_ch_item = _load_excel_with_colmap(gei)

    # 从 Excel 收集每个 product_code 的 size 集合（尽量用真实尺码；没有则用默认）
    code_sizes = {}
    code_first_channel = {}  # 保存一个渠道绑定（如有）
    for _, row in df.iterrows():
        sku_name_val = str(row.get(key_sku_name, "")).strip()
        parsed = split_sku_name(sku_name_val)
        if not parsed:
            continue
        code, size = parsed
        code_sizes.setdefault(code, set()).add(size)

        chp = str(row.get(key_ch_prod, "")).strip() if key_ch_prod else ""
        chi = str(row.get(key_ch_item, "")).strip() if key_ch_item else ""
        if chp or chi:
            code_first_channel.setdefault(code, (chp, chi))

    DEFAULT_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]

    missing_codes_cnt = 0
    inserted = 0
    conn = psycopg2.connect(**db)
    with conn:
        with conn.cursor() as cur:
            # 找已有的 product_code & (code,size)
            cur.execute(f"SELECT DISTINCT product_code FROM {table}")
            db_codes = {r[0] for r in cur.fetchall()}

            cur.execute(f"SELECT product_code,size FROM {table}")
            db_pairs = { (r[0], r[1]) for r in cur.fetchall() }

            for code, sizes in code_sizes.items():
                # 若整码缺失，记一次
                if code not in db_codes:
                    missing_codes_cnt += 1
                # 使用 Excel 提供的尺码，否则回退默认尺码
                sizes_to_use = sorted(sizes) if sizes else DEFAULT_SIZES
                chp, chi = code_first_channel.get(code, ("", ""))

                for size in sizes_to_use:
                    if (code, size) in db_pairs:
                        continue
                    cur.execute(
                        f"""INSERT INTO {table} (
                                product_code, product_url, size, gender,
                                stock_count, channel_product_id, channel_item_id,
                                is_published, last_checked
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,CURRENT_TIMESTAMP)
                            ON CONFLICT (product_code,size) DO NOTHING
                        """,
                        (code, "", size, None, 0, chp, chi)
                    )
                    inserted += cur.rowcount

    print(f"✅ 占位完成：新增记录 {inserted} 条（其中全新编码约 {missing_codes_cnt} 个）")

# ========= 方法 2：绑定 skuid/sku_name/item_id =========
def insert_jingyaid_to_db(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise RuntimeError(f"BRAND_CONFIG 未配置 {brand}")

    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    db    = cfg["PGSQL_CONFIG"]
    doc   = Path(cfg["BASE"]) / "document"
    out   = Path(cfg["OUTPUT_DIR"]); out.mkdir(parents=True, exist_ok=True)

    gei = find_latest_gei_file(doc)
    print(f"[绑定] 使用文件：{gei}")
    df, key_sku_id, key_sku_name, key_item_id, key_ch_prod, key_ch_item = _load_excel_with_colmap(gei)

    unparsed = []
    updated, skipped = 0, 0

    conn = psycopg2.connect(**db)
    with conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                skuid_val    = str(row.get(key_sku_id, "")).strip() if key_sku_id else ""
                sku_name_val = str(row.get(key_sku_name, "")).strip()
                item_id_val  = str(row.get(key_item_id, "")).strip() if key_item_id else ""

                parsed = split_sku_name(sku_name_val)
                if not parsed:
                    skipped += 1
                    unparsed.append({"sku名称": sku_name_val, "skuID": skuid_val, "货品id": item_id_val, "原因": "sku名称无法拆分"})
                    continue
                code, size = parsed

                # 动态拼接 SET 子句（支持 Excel 有/无 渠道列）
                # 动态拼接 SET 子句（支持 Excel 有/无 渠道列）
                set_clauses = ["item_id=%s", "skuid=%s", "sku_name=%s", "is_published=TRUE",
                               "last_checked=CURRENT_TIMESTAMP"]
                params = [item_id_val, skuid_val, sku_name_val]

                # 读取渠道两列（如有）
                chp = str(row.get(key_ch_prod, "")).strip() if key_ch_prod else ""
                chi_excel = str(row.get(key_ch_item, "")).strip() if key_ch_item else ""

                # ✅ 关键：优先用 Excel 的 channel_item_id；否则回退到 “货品id”
                chi_final = chi_excel or item_id_val

                # 只有有值才更新，避免把已有值覆写成空串
                if chp:
                    set_clauses.append("channel_product_id=%s")
                    params.append(chp)
                if chi_final:
                    set_clauses.append("channel_item_id=%s")
                    params.append(chi_final)

                set_sql = ", ".join(set_clauses)
                sql = f"UPDATE {table} SET {set_sql} WHERE product_code=%s AND size=%s"
                params.extend([code, size])

                cur.execute(sql, params)

                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1
                    unparsed.append({"sku名称": sku_name_val, "skuID": skuid_val, "货品id": item_id_val, "原因": "DB未找到对应 (product_code,size)"})

    print(f"✅ 绑定完成：成功 {updated} 条，未更新 {skipped} 条")
    if unparsed:
        out_xlsx = out / "unparsed_sku_names_barbour.xlsx"
        pd.DataFrame(unparsed).to_excel(out_xlsx, index=False)
        print(f"⚠️ 未更新列表已导出：{out_xlsx}")

# ========= CLI =========
if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) >= 2 else "barbour"
    mode  = sys.argv[2] if len(sys.argv) >= 3 else "all"   # all | missing | bind

    if mode == "missing":
        insert_missing_products_with_zero_stock(brand)
    elif mode == "bind":
        insert_jingyaid_to_db(brand)
    else:
        insert_missing_products_with_zero_stock(brand)
        insert_jingyaid_to_db(brand)
