# run_export_published_products.py
#
# 运营入口：导出品牌下所有已发布商品列表（渠道产品ID、商品编码、颜色）。
#
# 使用步骤：修改下方 BRANDS 后直接运行
# 输出：{品牌 OUTPUT_DIR}/published_products_{brand}.xlsx

from channels.jingya.export.export_published_products import export_published_products

# ==== 参数 ====
BRANDS = ["barbour", "camper", "clarks" ,"geox","ecco"]   # 可填多个，如 ["barbour", "camper", "geox"]
# ==============

if __name__ == "__main__":
    for brand in BRANDS:
        export_published_products(brand)
