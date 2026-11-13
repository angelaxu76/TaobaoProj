# -*- coding: utf-8 -*-
r"""
run_export_only.py
==================
Barbour 只导出库存 / 价格 Excel（不抓取、不导入 TXT）。

相当于 prepare_jingya_listing.py 只跑阶段 D（可选连同阶段 C），
不需要修改 session_config.py 里的 RUN_* 开关。

  默认（只跑 D）：直接读数据库 barbour_inventory 当前的价格/库存导出 Excel，
                  不写库。适用于上一次流水线已经跑完 C、只是想重新导一份 Excel。

  --with-c（先 C 后 D）：不重新导入 TXT（products/offers 保持不变），
                  但会根据数据库里已有的 offers 重建 barbour_inventory、重算
                  供应商组合/价格/库存，再导出。适用于：
                    - B 阶段导入过了但 C 还没跑；
                    - 更新了鲸芽商品 Excel（新发布商品）；
                    - 改了手动库存/手动价格清单、或定价参数。

导出路径与手动清单路径沿用 session_config.py 中的
STOCK_EXPORT_DIR / PRICE_EXPORT_DIR / STORE_PRICE_INPUT_DIR /
STORE_PRICE_OUTPUT_DIR / MANUAL_STOCK_XLSX / MANUAL_PRICE_XLSX。

用法（在项目根目录执行）：
  python -m brands.barbour.pipeline.run_export_only
  python -m brands.barbour.pipeline.run_export_only --with-c
"""
import sys
import time
from datetime import datetime

from brands.barbour.pipeline.prepare_jingya_listing import (
    _setup_file_log,
    run_c_inventory,
    run_d_export,
)


def main() -> None:
    with_c = "--with-c" in sys.argv

    _setup_file_log()
    start = time.time()
    print(f"\n{'★' * 60}")
    print(f"  Barbour 仅导出 Excel  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式：{'C（重算库存/价格）+ D（导出）' if with_c else '仅 D（直接导出数据库现有数据）'}")
    print(f"{'★' * 60}")

    if with_c:
        run_c_inventory()
    run_d_export()

    print(f"\n✅ 完成，总耗时 {(time.time() - start) / 60:.1f} 分钟\n")


if __name__ == "__main__":
    main()
