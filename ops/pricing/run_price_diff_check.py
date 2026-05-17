# -*- coding: utf-8 -*-
# 一键检查各品牌店铺 Excel 的一口价 vs 数据库价格差异 + 倒挂风险。
# 输入：GEI_SHARED/{品牌}/store_prices/ 下的所有 xlsx
# 输出：OUTPUT_BASE/{品牌}/ 下，文件名 = 原文件名 + SUFFIX + ".xlsx"
#
# 输出列：宝贝标题 | channel_product_id | product_code | 一口价
#         | taobao_store_price | jingya_untaxed_price | 差异百分比 | 倒挂安全比例
#
# 差异百分比   = (一口价 - taobao_store_price) / taobao_store_price * 100
#   正值 -> 店铺标价高于数据库目标价
#   负值 -> 店铺标价低于数据库目标价
#
# 倒挂安全比例 = (到手价 - 安全线) / 安全线    （> 0 才能卖，红色高亮警告）
#   到手价 = 一口价 * TAOBAO_DISCOUNT * TAX_FACTOR
#   安全线 = jingya_untaxed_price * (1 + MIN_PROFIT)
#
# 修改下面 [运行参数] 部分后直接运行即可。

from pathlib import Path

# ========== 运行参数（按需修改）==========

# 输出报告的根目录，每个品牌单独一个子目录
OUTPUT_BASE = Path(r"D:\TB\maintain\price_diff_report")

# 差异过滤阈值（百分比绝对值），低于此阈值且非倒挂的商品不输出
# 0.0 = 输出所有有差异的商品；5.0 = 只看差异超过 5% 的（倒挂行始终输出）
THRESHOLD = 0.0

# 输出文件名后缀
SUFFIX = "_差价"

# 黑名单 Excel（可选，设为 None 则不过滤）
# 如 BLACKLIST = r"\\vmware-host\Shared Folders\shared\clarks\exclude.xlsx"
BLACKLIST = None

# 倒挂计算参数（通常不需要修改）
TAOBAO_DISCOUNT = 0.85   # 淘宝平台扣点
TAX_FACTOR      = 0.9    # 关税/税费系数
MIN_PROFIT      = 0.03   # 最低利润率要求（3%）

# 要处理的品牌及其店铺导出目录（含多店铺 xlsx 时全部处理）
GEI_SHARED = Path(r"\\vmware-host\Shared Folders\shared")

BRAND_TASKS = [
    {"brand": "clarks",  "input_dir": GEI_SHARED / "clarks"  / "store_prices"},
    {"brand": "camper",  "input_dir": GEI_SHARED / "camper"  / "store_prices"},
    {"brand": "ecco",    "input_dir": GEI_SHARED / "ecco"    / "store_prices"},
    {"brand": "geox",    "input_dir": GEI_SHARED / "geox"    / "store_prices"},
    {"brand": "barbour", "input_dir": GEI_SHARED / "barbour" / "store_prices"},
]

# ========== 执行 ==========

from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import (
    compare_price_vs_db_bulk,
)


def run_all():
    print("=" * 60)
    print("  价格差异检查  一口价 vs 数据库 taobao_store_price")
    print("=" * 60)

    results = []
    for task in BRAND_TASKS:
        brand     = task["brand"]
        input_dir = Path(task["input_dir"])
        output_dir = OUTPUT_BASE / brand

        print(f"\n{'─'*50}")
        print(f"  品牌: {brand.upper()}")
        print(f"  输入: {input_dir}")
        print(f"  输出: {output_dir}")
        print(f"{'─'*50}")

        if not input_dir.exists():
            print(f"  [SKIP] 输入目录不存在，跳过。")
            results.append((brand, "skipped", "目录不存在"))
            continue

        try:
            compare_price_vs_db_bulk(
                brand=brand,
                input_dir=str(input_dir),
                output_dir=str(output_dir),
                suffix=SUFFIX,
                price_diff_threshold=THRESHOLD,
                blacklist_excel_file=BLACKLIST,
                taobao_discount=TAOBAO_DISCOUNT,
                tax_factor=TAX_FACTOR,
                min_profit=MIN_PROFIT,
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
            print(f"  ✅ {brand:<12}  报告已输出到 {OUTPUT_BASE / brand}")
        elif status == "skipped":
            print(f"  ⚠  {brand:<12}  {msg}")
        else:
            print(f"  ❌ {brand:<12}  {msg}")
    print()


if __name__ == "__main__":
    run_all()
