# -*- coding: utf-8 -*-
r"""
tool_export_price_stock_report.py
==================================
导出人可读的商品状态报表：每个已发布商品当前的
供货商组合 / 定价依据供货商 / 折扣率 / 售价 / 库存。

纯查询导出，不做任何计算、不写库——数据就是当前数据库里的实际状态。
核心逻辑见 brands/barbour/jingya/allocate_supplier_and_price.py 里的
export_price_stock_supplier_report()，这里只是一个方便直接运行的入口。

用法：
  python -m brands.barbour.pipeline.tool_export_price_stock_report
  python -m brands.barbour.pipeline.tool_export_price_stock_report --out D:\path\to\report.xlsx
  （不传 --out 时默认导出到 BARBOUR["OUTPUT_DIR"]，文件名带时间戳）
"""
import sys

from brands.barbour.jingya.allocate_supplier_and_price import (
    export_price_stock_supplier_report,
)


def main() -> None:
    output_path = None
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]
        else:
            print("⚠️ --out 后面缺少路径参数，将使用默认输出路径。")

    export_price_stock_supplier_report(output_path=output_path)


if __name__ == "__main__":
    main()
