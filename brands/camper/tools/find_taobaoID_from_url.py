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


def find_item_ids_from_url_links(brand: str):
    """
    提取链接中的商品编码 → 在店铺 Excel 中查找 item_id → 输出 Excel（含未匹配记录）。
    """
    brand = brand.lower()
    config = BRAND_CONFIG[brand]
    txt_path = Path(config["TXT_DIR"]).parent / "product_links.txt"
    output_path = Path(config["BASE"]) / "repulibcation" / f"{brand}_encoded_itemids.xlsx"
    unmatched_path = Path(config["BASE"]) / "repulibcation" / f"{brand}_未匹配商品编码.xlsx"
    store_dir = Path(config["STORE_DIR"])

    print("🟡 Step 1️⃣ 提取商品编码...")
    product_codes = extract_product_codes_from_txt(txt_path)
    print(f"✅ 提取 {len(product_codes)} 个商品编码")

    matched_codes = set()
    output_rows = []

    print("🟡 Step 2️⃣ 查找宝贝ID...")
    for store_subdir in store_dir.iterdir():
        if not store_subdir.is_dir():
            continue
        store_name = store_subdir.name
        for excel_file in store_subdir.glob("*.xls*"):
            if excel_file.name.startswith("~$"):
                continue
            print(f"📂 读取店铺 [{store_name}] 文件: {excel_file.name}")
            df = pd.read_excel(excel_file, dtype=str).fillna(method="ffill")

            for _, row in df.iterrows():
                code = str(row.get("商家编码", "")).strip()
                item_id = str(row.get("宝贝ID", "")).strip()
                if code in product_codes and item_id:
                    output_rows.append({
                        "商品编码": code,
                        "淘宝宝贝ID": item_id,
                        "店铺": store_name
                    })
                    matched_codes.add(code)

    # 输出匹配结果
    if output_rows:
        df_matched = pd.DataFrame(output_rows).drop_duplicates()
        df_matched.to_excel(output_path, index=False)
        print(f"✅ 匹配成功: {len(df_matched)} 条，已导出 → {output_path}")
    else:
        print("⚠️ 没有匹配到任何宝贝ID")

    # 输出未匹配编码
    unmatched_codes = sorted(set(product_codes) - matched_codes)
    if unmatched_codes:
        print(f"⚠️ 未匹配编码: {len(unmatched_codes)} 个 → 已导出: {unmatched_path}")
        df_unmatched = pd.DataFrame({"未匹配商品编码": unmatched_codes})
        df_unmatched.to_excel(unmatched_path, index=False)
    else:
        print("✅ 所有编码均已匹配")


from pathlib import Path
import pandas as pd
from config import BRAND_CONFIG


def find_item_ids_from_code_txt(brand: str, code_txt_path):
    """
    从指定 TXT 文件读取商品编码 → 按店铺匹配 → 每个店铺输出独立 TXT（只输出去重后的宝贝ID）
    """
    code_txt_path = Path(code_txt_path)
    brand = brand.lower()
    config = BRAND_CONFIG[brand]
    store_dir = Path(config["STORE_DIR"])
    output_dir = Path(config["BASE"]) / "repulibcation" / "matched_ids"
    output_dir.mkdir(parents=True, exist_ok=True)

    # === 读取编码列表 ===
    if not code_txt_path.exists():
        raise FileNotFoundError(f"❌ 编码文件不存在: {code_txt_path}")

    with code_txt_path.open("r", encoding="utf-8") as f:
        product_codes = sorted({line.strip() for line in f if line.strip()})
    print(f"✅ 从 TXT 提取 {len(product_codes)} 个商品编码")

    matched_total = 0
    unmatched_codes = set(product_codes)

    # === 遍历每个店铺 ===
    for store_subdir in store_dir.iterdir():
        if not store_subdir.is_dir():
            continue
        store_name = store_subdir.name
        store_matched = []

        for excel_file in store_subdir.glob("*.xls*"):
            if excel_file.name.startswith("~$"):
                continue
            print(f"📂 店铺 [{store_name}] → 读取: {excel_file.name}")
            df = pd.read_excel(excel_file, dtype=str).fillna(method="ffill")

            for _, row in df.iterrows():
                code = str(row.get("商家编码", "")).strip()
                item_id = str(row.get("宝贝ID", "")).strip()
                if code in product_codes and item_id:
                    store_matched.append(item_id)
                    unmatched_codes.discard(code)

        # 输出每个店铺自己的 matched.txt（去重宝贝ID）
        if store_matched:
            unique_item_ids = sorted(set(store_matched))
            txt_path = output_dir / f"{store_name}_matched.txt"
            with txt_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(unique_item_ids))
            print(f"✅ 店铺 [{store_name}] 匹配 {len(unique_item_ids)} 条，写入: {txt_path}")
            matched_total += len(unique_item_ids)
        else:
            print(f"⚠️ 店铺 [{store_name}] 无匹配")

    # 输出未匹配编码 TXT
    if unmatched_codes:
        unmatched_path = output_dir / f"{brand}_未匹配商品编码.txt"
        with unmatched_path.open("w", encoding="utf-8") as f:
            for code in sorted(unmatched_codes):
                f.write(code + "\n")
        print(f"⚠️ 未匹配编码 {len(unmatched_codes)} 个 → 已写入: {unmatched_path}")
    else:
        print("✅ 所有商品编码均已匹配完毕")

