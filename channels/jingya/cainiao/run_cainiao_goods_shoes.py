from pathlib import Path
from channels.jingya.cainiao.generate_goods_update_excel_shoes import export_goods_excel_from_db_shoes
from channels.jingya.cainiao.generate_binding_goods_excel_shoes import generate_channel_binding_excel_shoes


# 👇 选择品牌（取消注释其中一行）
BRAND = "camper"
# BRAND = "ecco"
# BRAND = "clarks"
# BRAND = "geox"

GOODS_DIR = Path("D:/TB/taofenxiao/goods")
GROUP_SIZE = 500


KNOWN_BRANDS = ("camper", "ecco", "clarks", "geox")


def check_brand_matches_goods_file():
    """货品导出文件名带品牌后缀时（如 ..._geox.xlsx），校验与 BRAND 一致，防止选错品牌"""
    files = sorted(GOODS_DIR.glob("货品导出*.xlsx"), reverse=True)
    if not files:
        return
    stem = files[0].stem.lower()
    file_brand = next((b for b in KNOWN_BRANDS if stem.endswith(f"_{b}")), None)
    if file_brand and file_brand != BRAND:
        raise SystemExit(
            f"❌ 品牌不一致：货品导出文件是 {file_brand}（{files[0].name}），但 BRAND = {BRAND}，请修改 BRAND"
        )


def run():
    check_brand_matches_goods_file()
    print(f"\n🚀 鲸芽菜鸟流程 — {BRAND} 货品更新 & 绑定")

    print(f"\n📦 导出 {BRAND} 货品导入 Excel（用于更新货品名称）")
    export_goods_excel_from_db_shoes(BRAND, GOODS_DIR, GROUP_SIZE)

    print(f"\n🔗 导出 {BRAND} 货品绑定 Excel")
    generate_channel_binding_excel_shoes(BRAND, GOODS_DIR)

    print("\n✅ 完成")


if __name__ == "__main__":
    run()
