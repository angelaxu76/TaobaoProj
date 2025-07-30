import pandas as pd
from pathlib import Path

def mark_offline_products_from_store_excels(config: dict):
    txt_dir: Path = config["TXT_DIR"]
    output_dir: Path = config["OUTPUT_DIR"]
    offline_codes = set()

    # 遍历所有店铺目录
    for store_dir in output_dir.iterdir():
        if not store_dir.is_dir():
            continue

        store_name = store_dir.name
        excel_files = list(store_dir.glob("*.xlsx"))
        if not excel_files:
            continue

        print(f"📂 解析店铺【{store_name}】Excel：{len(excel_files)} 个文件")

        store_codes = set()

        for excel_file in excel_files:
            try:
                df = pd.read_excel(excel_file)

                # 自动寻找包含“编码”的列，如“商家编码”、“商品编码”
                code_column = None
                for col in df.columns:
                    if "编码" in col:
                        code_column = col
                        break

                if code_column:
                    # ⚠️ 将 float → int → str，避免 "26175424.0" 的误判
                    for code in df[code_column].dropna():
                        try:
                            clean_code = str(int(float(code)))  # 去掉小数点
                            store_codes.add(clean_code)
                        except:
                            continue
                else:
                    print(f"⚠️ 未找到“编码”列: {excel_file.name}")

            except Exception as e:
                print(f"❌ 读取失败: {excel_file} - {e}")

        # 检查哪些商品编码在 TXT 中不存在
        for code in store_codes:
            txt_path = txt_dir / f"{code}.txt"
            if not txt_path.exists():
                offline_codes.add(code)

    # 输出结果
    if not offline_codes:
        print("✅ 没有发现需要下架的商品。")
        return

    df_out = pd.DataFrame({"下架商品编码": sorted(offline_codes)})

    excel_out = output_dir / "offline_products_from_store.xlsx"
    df_out.to_excel(excel_out, index=False)
    print(f"📦 共 {len(offline_codes)} 个商品在店铺中上架但 TXT 缺失，已导出: {excel_out}")

    txt_out = output_dir / "offline_products_from_store.txt"
    with open(txt_out, "w", encoding="utf-8") as f:
        for code in sorted(offline_codes):
            f.write(code + "\n")
    print(f"📝 TXT 同步导出: {txt_out}")
