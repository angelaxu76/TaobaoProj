# -*- coding: utf-8 -*-
"""
Barbour 日常运营流水线（单一入口）

对应操作步骤：
  1. [A] 抓取各供货商商品数据 → TXT 文件
  2. [B] TXT 导入 barbour_products + barbour_offers
  ── 此处人工操作：在鲸芽发布新商品，并更新本地鲸芽 Excel ──
  3. [C] 重建 supplier_map + barbour_inventory（新品建档 + 低库存换供应商，一次完成）
  4. [D] 导出库存/价格 Excel → 用于批量更新鲸芽

使用方式：
  - 修改下方 ══ CONFIG ══ 区域的开关 / 路径，然后直接运行此脚本。
  - 如果本次跳过某个阶段（例如 A 已跑过），将对应 RUN_* 设为 False 即可。
"""

import time
from datetime import datetime

# ══════════════════════════════════════════════════════════════════
#  CONFIG — 按需修改
# ══════════════════════════════════════════════════════════════════

# ── 阶段开关 ──────────────────────────────────────────────────────
RUN_A_CRAWL     = True   # 抓取供货商数据（耗时最长，若已抓过可关闭）
RUN_B_IMPORT    = True   # TXT 导入 products + offers
RUN_C_INVENTORY = True   # 重建 supplier_map + inventory
RUN_D_EXPORT    = True   # 导出库存 / 价格 Excel

# ── C 阶段：供应商策略参数 ────────────────────────────────────────
# 是否对低库存商品自动切换到更优供应商（True = 每次都执行）
C_REASSIGN_LOW_STOCK = True
# 有货尺码数低于此值时视为"低库存"，触发换供应商
C_SIZE_THRESHOLD     = 3

# ── 路径配置 ─────────────────────────────────────────────────────
EXCLUDE_LIST_XLSX    = r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
STOCK_EXPORT_DIR     = r"\\vmware-host\Shared Folders\VMShared\input"
PRICE_EXPORT_DIR     = r"D:\TB\Products\barbour\repulibcation\publication_prices"

# ── A 阶段：要抓取的供应商列表（注释掉的暂时停用）────────────────
A_SUPPLIERS = [
    "barbour",
    "outdoorandcountry",
    "allweathers",
    "houseoffraser",
    "terraces",
    "philipmorris",
    "cho",
    # "very",
]

# ── B 阶段：要导入的供应商列表 ────────────────────────────────────
B_SUPPLIERS = [
    "barbour",
    "outdoorandcountry",
    "allweathers",
    "houseoffraser",
    "terraces",
    "philipmorris",
    "cho",
    # "very",
]

# ══════════════════════════════════════════════════════════════════
#  工具：计时 + 步骤打印
# ══════════════════════════════════════════════════════════════════

def _banner(text: str):
    print(f"\n{'═'*60}")
    print(f"  {text}")
    print(f"{'═'*60}")

def _step(text: str):
    print(f"\n>>> {text}")

def _ok(text: str, elapsed: float):
    print(f"✅ {text}  ({elapsed:.1f}s)")

def _skip(text: str):
    print(f"⏭  跳过：{text}")

def _fail(step: str, exc: Exception):
    print(f"\n{'!'*60}")
    print(f"❌ [{step}] 失败，错误信息：")
    print(f"   {type(exc).__name__}: {exc}")
    print(f"{'!'*60}")
    raise SystemExit(f"流程中断于 [{step}]，请检查上方错误后重新运行。")


# ══════════════════════════════════════════════════════════════════
#  阶段 A：抓取供货商数据
# ══════════════════════════════════════════════════════════════════

def run_a_crawl():
    _banner("阶段 A：抓取供货商商品数据")

    from config import BARBOUR
    from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
    _step("备份并清空 publication / repulibcation 目录")
    backup_and_clear_brand_dirs(BARBOUR)

    from brands.barbour.supplier.barbour_get_links        import barbour_get_links
    from brands.barbour.supplier.barbour_fetch_info       import barbour_fetch_info
    from brands.barbour.supplier.outdoorandcountry_get_links  import outdoorandcountry_fetch_and_save_links
    from brands.barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
    from brands.barbour.supplier.allweathers_get_links    import allweathers_get_links
    from brands.barbour.supplier.allweathers_fetch_info   import allweathers_fetch_info
    from brands.barbour.supplier.houseoffraser_get_links  import houseoffraser_get_links
    from brands.barbour.supplier.houseoffraser_fetch_info import houseoffraser_fetch_info
    from brands.barbour.supplier.terraces_get_links       import collect_terraces_links
    from brands.barbour.supplier.terraces_fetch_info      import terraces_fetch_info
    from brands.barbour.supplier.philipmorrisdirect_get_links  import philipmorris_get_links
    from brands.barbour.supplier.philipmorrisdirect_fetch_info import philipmorris_fetch_info
    from brands.barbour.supplier.cho_get_links            import cho_get_links
    from brands.barbour.supplier.cho_fetch_info           import cho_fetch_info

    _FETCH_MAP = {
        "barbour":           (barbour_get_links,                  lambda: barbour_fetch_info()),
        "outdoorandcountry": (outdoorandcountry_fetch_and_save_links, lambda: outdoorandcountry_fetch_info(max_workers=1)),
        "allweathers":       (allweathers_get_links,              lambda: allweathers_fetch_info(7)),
        "houseoffraser":     (houseoffraser_get_links,            lambda: houseoffraser_fetch_info(max_workers=7, headless=False)),
        "terraces":          (collect_terraces_links,             lambda: terraces_fetch_info(max_workers=7)),
        "philipmorris":      (philipmorris_get_links,             lambda: philipmorris_fetch_info(max_workers=7)),
        "cho":               (cho_get_links,                      lambda: cho_fetch_info(max_workers=7)),
    }

    for supplier in A_SUPPLIERS:
        if supplier not in _FETCH_MAP:
            print(f"⚠️  未知供应商，跳过：{supplier}")
            continue

        get_links_fn, fetch_fn = _FETCH_MAP[supplier]

        _step(f"[{supplier}] 获取商品链接")
        t = time.time()
        try:
            get_links_fn()
            _ok(f"{supplier} 链接获取完成", time.time() - t)
        except Exception as e:
            _fail(f"A-get_links-{supplier}", e)

        _step(f"[{supplier}] 抓取商品详情 → TXT")
        t = time.time()
        try:
            fetch_fn()
            _ok(f"{supplier} 详情抓取完成", time.time() - t)
        except Exception as e:
            _fail(f"A-fetch_info-{supplier}", e)


# ══════════════════════════════════════════════════════════════════
#  阶段 B：TXT 导入数据库
# ══════════════════════════════════════════════════════════════════

def run_b_import():
    _banner("阶段 B：TXT 导入 barbour_products + barbour_offers")

    from brands.barbour.common.import_txt_to_products_v2 import batch_import_txt_to_barbour_product
    from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier

    _step("导入商品基础信息 → barbour_products")
    for supplier in B_SUPPLIERS:
        t = time.time()
        try:
            batch_import_txt_to_barbour_product(supplier)
            _ok(f"{supplier} → products 完成", time.time() - t)
        except Exception as e:
            _fail(f"B-products-{supplier}", e)

    _step("导入供应商库存/价格 → barbour_offers（含下架商品清零）")
    for supplier in B_SUPPLIERS:
        t = time.time()
        try:
            # full_sweep=True：本次是全量抓取，对整个供应商做完整软删除，
            # 确保本次没出现 TXT 的商品（已下架）stock_count 被清为 0
            import_txt_for_supplier(supplier, dryrun=False, full_sweep=True)
            _ok(f"{supplier} → offers 完成", time.time() - t)
        except Exception as e:
            _fail(f"B-offers-{supplier}", e)


# ══════════════════════════════════════════════════════════════════
#  阶段 C：重建 supplier_map + inventory（一次完成，不重复）
# ══════════════════════════════════════════════════════════════════

def run_c_inventory():
    _banner("阶段 C：重建 supplier_map + barbour_inventory")

    from brands.barbour.jingya.insert_jingyaid_mapping import (
        clear_barbour_inventory,
        insert_missing_products_with_zero_stock,
        insert_jingyaid_to_db,
    )
    from brands.barbour.common.build_supplier_jingya_mapping import (
        fill_supplier_map,
        reassign_low_stock_suppliers,
    )
    from brands.barbour.jingya.merge_offer_into_inventory import (
        backfill_barbour_inventory_single_supplier,
        merge_band_stock_into_inventory,
        apply_fixed_prices_from_excel,
    )

    # ── 步骤 C1：重建 inventory 骨架 ────────────────────────────────
    # 必须先建骨架，fill_supplier_map 才能读到 is_published=TRUE 的商品
    _step("C1：清空 barbour_inventory")
    try:
        clear_barbour_inventory()
    except Exception as e:
        _fail("C1-clear_inventory", e)

    _step("C2：插入鲸芽已发布商品（含新上架，stock=0 占位）")
    try:
        insert_missing_products_with_zero_stock("barbour")
    except Exception as e:
        _fail("C2-insert_missing", e)

    _step("C3：写入鲸芽 ID 映射（is_published=TRUE）")
    try:
        insert_jingyaid_to_db("barbour")
    except Exception as e:
        _fail("C3-jingya_id", e)

    # ── 步骤 C4：供应商映射 ─────────────────────────────────────────
    # force_refresh=False：只为"尚无供应商"的商品（新品）填充，不覆盖已有分配
    _step("C4：为新品填充 supplier_map（不重算已有映射）")
    t = time.time()
    try:
        fill_supplier_map(force_refresh=False, exclude_xlsx=EXCLUDE_LIST_XLSX)
        _ok("supplier_map 新品填充完成", time.time() - t)
    except Exception as e:
        _fail("C4-fill_supplier_map", e)

    # ── 步骤 C5（可选）：低库存商品换供应商 ───────────────────────────
    if C_REASSIGN_LOW_STOCK:
        _step(f"C5：低库存换供应商（有货尺码 < {C_SIZE_THRESHOLD} 时触发）")
        t = time.time()
        try:
            reassign_low_stock_suppliers(
                size_threshold=C_SIZE_THRESHOLD,
                dry_run=False,
                exclude_xlsx=EXCLUDE_LIST_XLSX,
            )
            _ok("低库存换供应商完成", time.time() - t)
        except Exception as e:
            _fail("C5-reassign_low_stock", e)
    else:
        _skip("C5：低库存换供应商（C_REASSIGN_LOW_STOCK=False）")

    # ── 步骤 C6：用最新 supplier_map 回填 inventory ─────────────────
    _step("C6：按 supplier_map 回填 inventory 价格 + 主库存")
    t = time.time()
    try:
        backfill_barbour_inventory_single_supplier()
        _ok("价格 + 主库存回填完成", time.time() - t)
    except Exception as e:
        _fail("C6-backfill", e)

    _step("C7：10% 价格带合并多站点库存")
    t = time.time()
    try:
        merge_band_stock_into_inventory(band_ratio=0.10)
        _ok("价格带合并完成", time.time() - t)
    except Exception as e:
        _fail("C7-merge_band", e)

    _step("C8：应用固定价格覆盖（来自 exclude_list.xlsx）")
    t = time.time()
    try:
        apply_fixed_prices_from_excel(
            code_col="商品编码",
            sheet_name=0,
            xlsx_path=EXCLUDE_LIST_XLSX,
            dry_run=False,
        )
        _ok("固定价格覆盖完成", time.time() - t)
    except Exception as e:
        _fail("C8-fixed_prices", e)


# ══════════════════════════════════════════════════════════════════
#  阶段 D：导出 Excel
# ══════════════════════════════════════════════════════════════════

def run_d_export():
    _banner("阶段 D：导出库存 / 价格 Excel")

    from channels.jingya.export.export_stock_to_excel import export_stock_excel
    from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices

    _step("导出库存 Excel → 用于鲸芽批量更新库存")
    t = time.time()
    try:
        export_stock_excel("barbour", STOCK_EXPORT_DIR)
        _ok(f"库存 Excel 已生成：{STOCK_EXPORT_DIR}", time.time() - t)
    except Exception as e:
        _fail("D-export_stock", e)

    _step("导出价格 Excel → 用于鲸芽批量更新价格")
    t = time.time()
    try:
        export_jiangya_channel_prices(brand="barbour", output_dir=PRICE_EXPORT_DIR)
        _ok(f"价格 Excel 已生成：{PRICE_EXPORT_DIR}", time.time() - t)
    except Exception as e:
        _fail("D-export_price", e)


# ══════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════

def main():
    start = time.time()
    print(f"\n{'★'*60}")
    print(f"  Barbour 日常流水线  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'★'*60}")

    if RUN_A_CRAWL:
        run_a_crawl()
    else:
        _skip("阶段 A（RUN_A_CRAWL=False）")

    if RUN_B_IMPORT:
        run_b_import()
    else:
        _skip("阶段 B（RUN_B_IMPORT=False）")

    if RUN_C_INVENTORY:
        print("\n" + "─"*60)
        print("  ⚠️  即将执行阶段 C：请确认已完成以下人工操作：")
        print("     1. 在鲸芽发布需要上架的新商品")
        print("     2. 将最新的鲸芽商品 Excel 下载并放置到对应目录")
        print("─"*60)
        run_c_inventory()
    else:
        _skip("阶段 C（RUN_C_INVENTORY=False）")

    if RUN_D_EXPORT:
        run_d_export()
    else:
        _skip("阶段 D（RUN_D_EXPORT=False）")

    total = time.time() - start
    print(f"\n{'★'*60}")
    print(f"  ✅ 全部完成！总耗时 {total/60:.1f} 分钟")
    print(f"{'★'*60}\n")


if __name__ == "__main__":
    main()
