# -*- coding: utf-8 -*-
# 一键为多个品牌生成"淘宝店铺价格导入表"（宝贝id | skuid | 调整后价格）。
# 输入：GEI_SHARED/{品牌}/store_prices/ 下的所有店铺导出 xlsx
# 黑名单：GEI_SHARED/{品牌}/exclude.xlsx（存在则启用，不存在则忽略）
# 输出：OUTPUT_BASE/{品牌}/ 下，文件名 = 原文件名 + "_price.xlsx"
#
# 各品牌原本分散在 brands/{brand}/pipeline/prepare_jingya_listing.py 里单独调用，
# 这里集中到一个脚本，方便一次性跑完所有品牌。
#
# 修改下面 [运行参数] 部分后直接运行即可。

from pathlib import Path

# ========== 运行参数（按需修改）==========

# 输入根目录：本机挂载的共享盘，对应 VM 里的 \\vmware-host\Shared Folders\shared
GEI_SHARED = Path(r"E:\shared\GEI_SHARED")

# 输出根目录：桌面下新建一个目录，每个品牌单独一个子目录
OUTPUT_BASE = Path.home() / "Desktop" / "店铺价格导出"

# 输出文件名后缀
SUFFIX = "_价格"

# 缺价的行是否丢弃：False = 保留该行，价格留空
DROP_ROWS_WITHOUT_PRICE = False

# 要处理的品牌及其店铺导出目录 / 黑名单文件
BRAND_TASKS = [
    {"brand": "clarks", "input_dir": GEI_SHARED / "clarks" / "store_prices", "blacklist": GEI_SHARED / "clarks" / "exclude.xlsx"},
    {"brand": "camper",  "input_dir": GEI_SHARED / "camper"  / "store_prices", "blacklist": GEI_SHARED / "camper"  / "exclude.xlsx"},
    {"brand": "ecco",    "input_dir": GEI_SHARED / "ecco"    / "store_prices", "blacklist": GEI_SHARED / "ecco"    / "exclude.xlsx"},
    {"brand": "geox",    "input_dir": GEI_SHARED / "geox"    / "store_prices", "blacklist": GEI_SHARED / "geox"    / "exclude.xlsx"},
]

# ========== 执行 ==========

from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import (
    generate_price_excels_bulk,
)


def run_all():
    print("=" * 60)
    print("  批量生成淘宝店铺价格导入表")
    print("=" * 60)

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    results = []
    for task in BRAND_TASKS:
        brand = task["brand"]
        input_dir = Path(task["input_dir"])
        blacklist = Path(task["blacklist"])
        output_dir = OUTPUT_BASE / brand

        print(f"\n{'─'*50}")
        print(f"  品牌: {brand.upper()}")
        print(f"  输入: {input_dir}")
        print(f"  黑名单: {blacklist if blacklist.exists() else '未找到，不启用'}")
        print(f"  输出: {output_dir}")
        print(f"{'─'*50}")

        if not input_dir.exists():
            print(f"  [SKIP] 输入目录不存在，跳过。")
            results.append((brand, "skipped", "输入目录不存在"))
            continue

        try:
            generate_price_excels_bulk(
                brand=brand,
                input_dir=str(input_dir),
                output_dir=str(output_dir),
                suffix=SUFFIX,
                drop_rows_without_price=DROP_ROWS_WITHOUT_PRICE,
                blacklist_excel_file=str(blacklist) if blacklist.exists() else None,
            )
            results.append((brand, "ok", None))
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append((brand, "error", str(e)))

    # 汇总
    print(f"\n{'=' * 60}")
    print("  完成汇总")
    print(f"{'=' * 60}")
    for brand, status, msg in results:
        if status == "ok":
            print(f"  ✅ {brand:<12}  已输出到 {OUTPUT_BASE / brand}")
        elif status == "skipped":
            print(f"  ⚠  {brand:<12}  {msg}")
        else:
            print(f"  ❌ {brand:<12}  {msg}")
    print()


if __name__ == "__main__":
    run_all()
