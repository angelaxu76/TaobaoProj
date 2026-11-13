# -*- coding: utf-8 -*-
r"""
run_export_only.py
==================
Barbour 不抓取、不导入 TXT，直接重算库存/价格并导出 Excel。

相当于 prepare_jingya_listing.py 只跑阶段 C + D（跳过 A、B），
不需要修改 session_config.py 里的 RUN_* 开关。

  阶段 C（RUN_C_INVENTORY=True，默认）：
      不读 TXT，products/offers 保持不变；读取最新的鲸芽商品 Excel
      （GEI@sales_catalogue_export@*.xlsx），重建 barbour_inventory、
      重算供应商组合/价格/库存。适用于：
        - 在鲸芽发布了新商品，并下载了新的鲸芽商品 Excel；
        - B 阶段导入过了但 C 还没跑；
        - 改了手动库存/手动价格清单、或定价参数。

  阶段 D：导出库存 Excel、鲸芽价格 Excel、淘宝店铺价格 Excel。

如果上一次已经跑完 C、只想重新导一份 Excel，把下面的 RUN_C_INVENTORY
改为 False，或命令行加 --skip-c。

导出路径与手动清单路径沿用 session_config.py 中的
STOCK_EXPORT_DIR / PRICE_EXPORT_DIR / STORE_PRICE_INPUT_DIR /
STORE_PRICE_OUTPUT_DIR / MANUAL_STOCK_XLSX / MANUAL_PRICE_XLSX。

用法（在项目根目录执行）：
  python -m brands.barbour.pipeline.run_export_only            # C + D
  python -m brands.barbour.pipeline.run_export_only --skip-c   # 只跑 D
"""
import sys
import time
from datetime import datetime

from brands.barbour.pipeline.prepare_jingya_listing import (
    _setup_file_log,
    run_c_inventory,
    run_d_export,
)

# ══ CONFIG ══
RUN_C_INVENTORY = True   # True = 先重算库存/价格（阶段 C）再导出；False = 只导出（阶段 D）


def main() -> None:
    run_c = RUN_C_INVENTORY and "--skip-c" not in sys.argv

    _setup_file_log()
    start = time.time()
    print(f"\n{'★' * 60}")
    print(f"  Barbour 重算并导出 Excel  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式：{'C（重算库存/价格）+ D（导出）' if run_c else '仅 D（直接导出数据库现有数据）'}")
    print(f"{'★' * 60}")

    if run_c:
        print("\n" + "─" * 60)
        print("  ⚠️  阶段 C 前请确认：")
        print("     1. 已在鲸芽发布需要上架的新商品")
        print("     2. 最新的鲸芽商品 Excel（GEI@sales_catalogue_export@*.xlsx）已放到对应目录")
        print("─" * 60)
        run_c_inventory()
    run_d_export()

    print(f"\n✅ 完成，总耗时 {(time.time() - start) / 60:.1f} 分钟\n")


if __name__ == "__main__":
    main()
