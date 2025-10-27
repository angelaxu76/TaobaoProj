from pathlib import Path
from jingya.cainiao_generate_excel_update_goods_excel import export_goods_excel_from_db
from jingya.cainiao_generate_excel_update_goods_for_shoe import export_goods_excel_from_db_shoes
from jingya.cainiao_generate_excel_binding_goods_shoe import generate_channel_binding_excel_shoes
from jingya.cainiao_generate_excel_binding_goods_jingya import generate_channel_binding_excel

 
def pipeline_jingya():
    print("\n🚀 鲸芽和菜鸟整合流程")

    #导出 货品导入excel，用于更新货品
    print("\n🌐导出 货品导入excel，用于更新货品")
    # BRAND = "clarks_jingya"  # 👈 品牌名（必须是 config.py 中 BRAND_CONFIG 的 key）
    # BRAND = "clarks_jingya"  # 👈 品牌名（必须是 config.py 中 BRAND_CONFIG 的 key）
    # GOODS_DIR = Path("D:/TB/taofenxiao/goods")  # 👈 Excel 文件所在目录（自动查找以“货品导出”开头的文件）
    # GROUP_SIZE = 500  # 👈 每个输出 Excel 的最大记录数
    # export_goods_excel_from_db_shoes(BRAND, GOODS_DIR, GROUP_SIZE)

    # # 导出 货品绑定的excel
    # generate_channel_binding_excel_shoes(BRAND, Path("D:/TB/taofenxiao/goods"))

    # print("\n🌐导出 barbour，用于更新货品")
    export_goods_excel_from_db("barbour", Path("D:/TB/taofenxiao/goods"), 500)
    generate_channel_binding_excel("barbour", Path("D:/TB/taofenxiao/goods"))

if __name__ == "__main__":
    pipeline_jingya()