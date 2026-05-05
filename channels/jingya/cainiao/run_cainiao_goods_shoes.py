from pathlib import Path
from channels.jingya.cainiao.generate_goods_update_excel_shoes import export_goods_excel_from_db_shoes
from channels.jingya.cainiao.generate_binding_goods_excel_shoes import generate_channel_binding_excel_shoes


# 👇 选择品牌（取消注释其中一行）
# BRAND = "camper"
BRAND = "ecco"
# BRAND = "clarks"

GOODS_DIR = Path("D:/TB/taofenxiao/goods")
GROUP_SIZE = 500


def run():
    print(f"\n🚀 鲸芽菜鸟流程 — {BRAND} 货品更新 & 绑定")

    print(f"\n📦 导出 {BRAND} 货品导入 Excel（用于更新货品名称）")
    export_goods_excel_from_db_shoes(BRAND, GOODS_DIR, GROUP_SIZE)

    print(f"\n🔗 导出 {BRAND} 货品绑定 Excel")
    generate_channel_binding_excel_shoes(BRAND, GOODS_DIR)

    print("\n✅ 完成")


if __name__ == "__main__":
    run()
