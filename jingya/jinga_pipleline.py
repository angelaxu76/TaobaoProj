from pathlib import Path
from jingya.cainiao_generate_excel_update_goods_excel import export_goods_excel_from_db

def pipeline_jingya():
    print("\n🚀 鲸芽和菜鸟整合流程")

    #导出 货品导入excel，用于更新货品
    print("\n🌐导出 货品导入excel，用于更新货品")
    BRAND = "clarks_jingya"  # 👈 品牌名（必须是 config.py 中 BRAND_CONFIG 的 key）
    GOODS_DIR = Path("D:/TB/taofenxiao/goods")  # 👈 Excel 文件所在目录（自动查找以“货品导出”开头的文件）
    GROUP_SIZE = 500  # 👈 每个输出 Excel 的最大记录数
    export_goods_excel_from_db(BRAND, GOODS_DIR, GROUP_SIZE)




if __name__ == "__main__":
    pipeline_jingya()