# run_check_jingya_stock.py
#
# 运营入口：核对数据库库存 vs 鲸芽最新导出Excel库存（按 skuid 匹配）。
#
# 使用步骤：
#   1. 修改下方 brand_name，运行本脚本
#   2. 默认会自动去 E:\shared\GEI_SHARED\<品牌>\ 下查找最新的鲸芽导出文件
#      （GEI@sales_catalogue_export@...xlsx）；如需使用手动下载的其他文件，
#      传入 jingya_excel_path 覆盖
#   3. 差异报告默认输出到 D:\TB\Products\<品牌>\document\stock_check\ 下；
#      如需指定输出路径，传入 output_report_path（需用关键字参数，见下方示例）

from channels.jingya.check.check_jingya_stock_mismatch import check_jingya_stock_mismatch
from config import DESKTOP_DIR

if __name__ == "__main__":
    brand = "clarks"  # 修改为对应品牌
    check_jingya_stock_mismatch(
        brand,
        # jingya_excel_path=r"D:\Downloads\GEI@sales_catalogue_export@xxx.xlsx",  # 可选：手动指定Excel
        output_report_path=str(DESKTOP_DIR / f"{brand}_stock_diff.xlsx"),  # 可选：指定输出路径
    )

