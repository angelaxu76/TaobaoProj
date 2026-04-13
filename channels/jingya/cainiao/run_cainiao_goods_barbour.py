from pathlib import Path
from channels.jingya.cainiao.generate_goods_update_excel import export_goods_excel_from_db
from channels.jingya.cainiao.generate_binding_goods_excel import generate_channel_binding_excel


GOODS_DIR = Path("D:/TB/taofenxiao/goods")
GROUP_SIZE = 500


def run():
    print("\n🚀 鲸芽菜鸟流程 — Barbour 货品更新 & 绑定")

    print("\n📦 导出 Barbour 货品导入 Excel（用于更新货品名称）")
    export_goods_excel_from_db("barbour", GOODS_DIR, GROUP_SIZE)

    print("\n🔗 导出 Barbour 货品绑定 Excel")
    generate_channel_binding_excel("barbour", GOODS_DIR)

    print("\n✅ 完成")


if __name__ == "__main__":
    run()
