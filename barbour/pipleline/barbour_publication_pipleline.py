from pathlib import Path
from barbour.generate_barbour_publication_excel import generate_publication_excel


def pipeline_barbour():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")


    # 步骤 1：将产品的编码放到D:\TB\Products\barbour\repulibcation\codes.txt
    # 步骤 2：生成发布产品的excel
    print("\n🌐 步骤 1：抓取商品链接")
    generate_publication_excel()

    print("\n步骤 2：生成透明图+背景图")