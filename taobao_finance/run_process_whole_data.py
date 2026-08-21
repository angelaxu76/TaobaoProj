from pathlib import Path

from taobao_finance.import_transaction_to_db import import_transaction
from taobao_finance.import_jingya_to_db import import_jingya_profit
from taobao_finance.enrich_taobao_submited_excel import enrich_excel
from sqlalchemy import create_engine, text
from cfg.db_config import PGSQL_CONFIG


def truncate_order_table():
    cfg = PGSQL_CONFIG
    engine = create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE taobao_order_logistics RESTART IDENTITY;"))
    print("🗑️  taobao_order_logistics 已清空")


# ============================================================
# 切换账号 / 月份：只需要改这两个变量
# ============================================================
# ACCOUNT = "五小剑"           # 或 "英国伦敦代购"
ACCOUNT = "英国伦敦代购"           # 或 "英国伦敦代购"
FOLDER_MONTH = "202512"      # 数据文件夹月份，对应 D:\TB\淘宝会计统计数据\{FOLDER_MONTH}\{ACCOUNT}

# 税务局申报涉及的月份（通常是该季度的三个月，与文件夹月份不一定一致，需单独确认）
# TAX_MONTHS = ["202507", "202508", "202509"]
TAX_MONTHS = ["202601", "202602", "202603"]

# ============================================================

# BASE_DIR = Path(r"D:\TB\淘宝会计统计数据\数据统计") / FOLDER_MONTH / ACCOUNT
BASE_DIR = Path(r"D:\TB\淘宝税务申报统计\淘宝会计统计数据202603\数据统计\英国伦敦代购") 

# 步骤 1：自动扫描"淘宝交易记录"文件夹下所有订单导出文件（.csv / .xlsx）
TAOBAO_EXCELS = [
    str(p) for p in sorted((BASE_DIR / "淘宝交易记录").glob("*"))
    if p.suffix.lower() in (".csv", ".xlsx")
]

# 步骤 2：自动扫描"鲸芽交易记录"文件夹（预期只有一个文件）
_jingya_candidates = sorted((BASE_DIR / "鲸芽交易记录").glob("*.xlsx"))
JINGYA_EXCEL = str(_jingya_candidates[0]) if _jingya_candidates else None

# 步骤 3：税务局推送的申报 Excel，按 TAX_MONTHS 自动拼接路径
_TAX_DIR = BASE_DIR / "淘宝财务数据"
TAX_EXCELS = [
    (
        str(_TAX_DIR / f"交易货款_{m}_{m}.csv"),
        str(_TAX_DIR / f"交易货款_{m}_{m}_enriched.xlsx"),
    )
    for m in TAX_MONTHS
]


def main():
    print("=" * 60)
    print(f"当前账号: {ACCOUNT}　|　数据文件夹月份: {FOLDER_MONTH}")
    print("=" * 60)

    if not TAOBAO_EXCELS:
        raise FileNotFoundError(f"未在 {BASE_DIR / '淘宝交易记录'} 找到任何 .csv/.xlsx 文件")
    if not JINGYA_EXCEL:
        raise FileNotFoundError(f"未在 {BASE_DIR / '鲸芽交易记录'} 找到任何 .xlsx 文件")

    print("📌 淘宝订单文件：")
    for p in TAOBAO_EXCELS:
        print(f"   {p}")
    print(f"📌 鲸芽分销文件：{JINGYA_EXCEL}")
    print("📌 税务申报文件：")
    for input_path, _ in TAX_EXCELS:
        print(f"   {input_path}")

    print()
    print("=" * 60)
    print("准备：清空 taobao_order_logistics 表")
    print("=" * 60)
    truncate_order_table()

    print()
    print("=" * 60)
    print(f"步骤 1/3：导入淘宝订单数据到数据库（共 {len(TAOBAO_EXCELS)} 个文件）")
    print("=" * 60)
    for path in TAOBAO_EXCELS:
        print(f"\n📂 处理: {path}")
        import_transaction(path)

    print()
    print("=" * 60)
    print("步骤 2/3：导入鲸芽分销利润到数据库")
    print("=" * 60)
    import_jingya_profit(JINGYA_EXCEL)

    print()
    print("=" * 60)
    print(f"步骤 3/3：生成补充后的申报 Excel（共 {len(TAX_EXCELS)} 个月）")
    print("=" * 60)
    for input_path, output_path in TAX_EXCELS:
        print(f"\n📂 处理: {input_path}")
        enrich_excel(input_path, output_path)

    print()
    print("✅ 全部完成！输出文件：")
    for _, output_path in TAX_EXCELS:
        print(f"   {output_path}")


if __name__ == "__main__":
    main()
