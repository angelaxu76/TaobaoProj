"""
把修改过的黑名单 Excel 导回数据库（一般先用 run_export_blocklist_excel.py 导出再改）。

读取列：商品编码（必填）、品牌、启用、打折后可发布、原因、备注；其它列忽略。
  - 表里没有的编码 → 新增（来源 excel_import）
  - 空单元格不覆盖数据库原值
  - 启用 = 否 → 解除拦截；启用 = 是 → 重新拦截；空 → 不变（新增编码默认启用）
不会删除 Excel 里没有出现的编码。
"""
from pathlib import Path

from common.publication.publish_blocklist import upsert_blocklist, set_active
from ops.blocklist.blocklist_excel import read_import_excel

INPUT_EXCEL = Path(r"E:\shared\GEI_SHARED\publish_blocklist_export_20261121.xlsx")  # 修改为实际文件

if __name__ == "__main__":
    df = read_import_excel(INPUT_EXCEL)
    print(f"📥 读取 {len(df)} 行：{INPUT_EXCEL}")

    rows = [
        {k: v for k, v in r.items() if k != "is_active"} | {"source": "excel_import"}
        for r in df.to_dict("records")
    ]
    upsert_blocklist(rows, count_as_new_block=False, reactivate=False)
    if "is_active" in df.columns:
        set_active(df.loc[df["is_active"] == True, "product_code"], True)    # noqa: E712
        set_active(df.loc[df["is_active"] == False, "product_code"], False)  # noqa: E712
