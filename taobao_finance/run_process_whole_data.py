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
# 英国伦敦代购
# ============================================================

# 步骤 1：淘宝后台导出的订单 Excel，可多个（按月分开下载的都列在这里）
# TAOBAO_EXCELS = [
#     r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝交易记录\ExportOrderList26242309550.xlsx",
#     r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝交易记录\ExportOrderList202604090721.csv",
#     # r"D:\OneDrive\Documentation\淘宝会计统计数据\ExportOrderList_202511.xlsx",
# ]

# # 步骤 2：鲸芽后台导出的分销数据 Excel（含分销利润）
# JINGYA_EXCEL = r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\鲸芽交易记录\jingya_202603.xlsx"

# # 步骤 3：税务局推送的申报 Excel，每个季度通常 3 个月
# # 格式：(输入路径, 输出路径)
# TAX_EXCELS = [
#     (
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202601_202601.csv",
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202601_202601_enriched.xlsx",
#     ),
#     (
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202602_202602.csv",
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202602_202602_enriched.xlsx",
#     ),
#     (
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202603_202603.csv",
#         r"D:\TB\淘宝会计统计数据\202603\英国伦敦代购\淘宝财务数据\交易货款_202603_202603_enriched.xlsx",
#     ),
# ]

# ============================================================

# ============================================================
# 五小剑
# ============================================================

# 步骤 1：淘宝后台导出的订单 Excel，可多个（按月分开下载的都列在这里）
TAOBAO_EXCELS = [
    r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝交易记录\ExportOrderList26313048433.xlsx",
    r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝交易记录\ExportOrderList202604090741.csv",
    # r"D:\OneDrive\Documentation\淘宝会计统计数据\ExportOrderList_202511.xlsx",
]

# 步骤 2：鲸芽后台导出的分销数据 Excel（含分销利润）
JINGYA_EXCEL = r"D:\TB\淘宝会计统计数据\202603\五小剑\鲸芽交易记录\jingya_202603.xlsx"

# 步骤 3：税务局推送的申报 Excel，每个季度通常 3 个月
# 格式：(输入路径, 输出路径)
TAX_EXCELS = [
    (
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202601_202601.csv",
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202601_202601_enriched.xlsx",
    ),
    (
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202602_202602.csv",
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202602_202602_enriched.xlsx",
    ),
    (
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202603_202603.csv",
        r"D:\TB\淘宝会计统计数据\202603\五小剑\淘宝财务数据\交易货款_202603_202603_enriched.xlsx",
    ),
]

# ============================================================

def main():
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
