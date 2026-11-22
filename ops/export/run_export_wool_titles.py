# run_export_wool_titles.py
#
# 运营入口：导出各品牌【已发布】且含羊绒类材质（wool/cashmere/merino/lambswool…）商品的
# 最新标题 + 渠道产品ID，用于在鲸芽/淘宝后台批量改标题。
#
# 使用步骤：修改下方参数后直接运行
# 输出：{OUTPUT_DIR}/羊绒商品标题_YYYYMMDD_HHMM.xlsx（每个品牌一个 sheet）

from channels.jingya.export.export_wool_titles import export_wool_titles

# ==== 参数 ====
BRANDS = ["camper", "clarks", "ecco", "geox", "barbour", "toast"]
OUTPUT_DIR = r"D:\TB\Products\wool_titles"
# ==============

if __name__ == "__main__":
    export_wool_titles(BRANDS, OUTPUT_DIR)
