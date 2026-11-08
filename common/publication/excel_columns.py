# -*- coding: utf-8 -*-
"""
发布 Excel 的统一列名（UiPath 按列名读取，所有品牌 / 品类必须一致）。

所有发布脚本都从这里引用列名，不要在脚本里手写：
  - channels/jingya/export/generate_publication_excel_shoes.py
  - channels/jingya/export/generate_publication_excel_v2.py
  - channels/jingya/export/generate_publication_excel_outerwear.py
  - brands/barbour/common/generate_publication_excel.py
"""

COLOR_COLUMN = "颜色"
LAUNCH_SEASON_COLUMN = "上市年份季节"
MATERIAL_COLUMN = "材质"   # 鞋：鞋面材质；服装：表面面料
