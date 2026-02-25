# run_zero_stock_offline.py
#
# 运营入口：将"长期无浏览/无点击"商品的所有尺码库存在数据库中设为 0（手动下架）。
#
# 使用步骤：
#   1. 从生意参谋 / 商品分析报表中找出需要下架的商品编码
#   2. 将 product_code 每行一个保存到 TXT 文件
#   3. 修改下方 brand_name 和 input_txt_path，运行本脚本

from channels.jingya.maintenance.zero_stock_by_codes import zero_stock_by_codes

if __name__ == "__main__":
    zero_stock_by_codes(
        brand_name="clarks_jingya",                          # 修改为对应品牌
        input_txt_path=r"g:\temp\offline_codes.txt",  # 修改为实际 TXT 路径
    )
