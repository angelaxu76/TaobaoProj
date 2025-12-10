from pathlib import Path
from finance.ingest.manage_export_shipments_costs import import_poe_cost_from_excel

# 这里就是你现在放 Excel 模板的目录
BASE_DIR = Path(r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES")


def main():
    # 找到所有 *_costs.xlsx 的文件
    excel_files = sorted(BASE_DIR.glob("*_costs.xlsx"))

    if not excel_files:
        print(f"[WARN] 目录下没有找到 *_costs.xlsx 文件：{BASE_DIR}")
        return

    print("==============================================")
    print(f"[INFO] 在目录中找到 {len(excel_files)} 个成本模板文件：")
    for f in excel_files:
        print("   -", f.name)
    print("==============================================")

    for f in excel_files:
        print(f"\n[RUN] 正在导入：{f.name}")
        try:
            # 关键：传入已经填写好的 Excel 路径，函数负责写入数据库
            import_poe_cost_from_excel(str(f))
            print(f"[OK] 导入完成：{f.name}")
        except Exception as e:
            print(f"[ERROR] 导入失败：{f.name}，错误：{e}")

    print("\n[DONE] 所有 *_costs.xlsx 处理完成。")


if __name__ == "__main__":
    main()
