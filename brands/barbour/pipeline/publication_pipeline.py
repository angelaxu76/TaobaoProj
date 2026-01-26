from pathlib import Path
from config import BARBOUR
from brands.barbour.common.generate_barbour_publication_excel import generate_publication_excel
from brands.barbour.common.export_barbour_discounts import export_barbour_discounts_excel,export_barbour_discounts_excel_multi

def pipeline_barbour():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")

    # 步骤 1：导出打折的商品可以发布的商品列表到excel


    # women ：LSP，LWX，LQU
    # excel_path = export_barbour_discounts_excel(0, 3, "LWX")
    # print(excel_path)

    # excel_path = export_barbour_discounts_excel_multi(0, 3, "LWX,LSP,LWX,LWB,LCA,LOL")

    excel_path = export_barbour_discounts_excel_multi(0, 3, "MWX,MQU,MOL,MWB,MFL,MOS")
    print(excel_path)

    # 步骤 1：将产品的编码放到D:\TB\Products\barbour\repulibcation\codes.txt
    # 步骤 2：生成发布产品的excel
    # print("\n🌐 步骤 1：抓取商品链接")
    # generate_publication_excel()




if __name__ == "__main__":
    pipeline_barbour()