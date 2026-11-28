from pathlib import Path
from cainiao.generate_goods_update_excel import export_goods_excel_from_db
from cainiao.generate_binding_goods_excel import generate_channel_binding_excel

# 用法：split_excel_by_brand.py 拆出的 “货品导出…_toast.xlsx” 放到 GOODS_DIR 后运行
# （目录里只放 toast 这一份货品导出；品类映射/包装规格见 cainiao/toast_goods_type.py）
GOODS_DIR = Path("D:/TB/taofenxiao/goods")
GROUP_SIZE = 500


def run():
    print("\n🚀 鲸芽菜鸟流程 — TOAST 货品更新 & 绑定")

    print("\n📦 导出 TOAST 货品导入 Excel（用于更新货品名称）")
    export_goods_excel_from_db("toast", GOODS_DIR, GROUP_SIZE)

    print("\n🔗 导出 TOAST 货品绑定 Excel")
    generate_channel_binding_excel("toast", GOODS_DIR)

    print("\n✅ 完成")


if __name__ == "__main__":
    run()
