"""
Barbour 供应商 & Inventory 导入总控脚本（重构版）

场景说明（按实际需要修改 MODE 即可）：

1) full_rebuild
   - 场景：数据库结构 & offers 都已经准备好，需要「从头重新建立」supplier_map + inventory。
   - 动作：
        a) 清空 inventory
        b) 插入鲸芽已发布商品（insert_missing_products_with_zero_stock）
        c) 写入 jingya_id 映射
        d) 重新计算 supplier_map（force_refresh=True）
        e) 单一最佳供货商回填 inventory（价格 + 主站点库存）
        f) 10% 价格带库存合并（多站点并集）

2) refresh_inventory
   - 场景：已经有 supplier_map，只是各个供货商 TXT/价格/库存更新了，想「按当前 map 重建 inventory」。
   - 动作：
        a) 清空 inventory
        b) 插入鲸芽已发布商品
        c) 写入 jingya_id 映射
        d) 单一最佳供货商回填 inventory
        e) 10% 价格带库存合并

3) after_new_publish
   - 场景：鲸芽上新了部分条码（新增商品），需要：
        - 为新商品绑定供货商
        - 并为所有商品重建 inventory
   - 动作：
        a) 清空 inventory
        b) 插入鲸芽已发布商品（包含新上的）
        c) 写入 jingya_id 映射
        d) 只对「未在 map 中的商品」填充 supplier_map（force_refresh=False）
        e) 单一最佳供货商回填 inventory
        f) 10% 价格带库存合并

4) reassign_low_stock_preview
   - 场景：想先预览「低尺码商品换供货商」的建议，不改数据库。
   - 动作：
        a) 运行 reassign_low_stock_suppliers(dry_run=True)，打印建议，不动 map/inventory

5) reassign_low_stock_apply
   - 场景：确认建议没问题，真正更新 supplier_map，并重新生成 inventory。
   - 动作：
        a) 运行 reassign_low_stock_suppliers(dry_run=False)
        b) 清空 inventory
        c) 插入鲸芽已发布商品
        d) 写入 jingya_id 映射
        e) 单一最佳供货商回填 inventory
        f) 10% 价格带库存合并

6) supplier_overrides
   - 场景：用手工 Excel 覆盖部分重点款式的供应商，然后重建 inventory。
   - 动作：
        a) 读取 barbour_supplier.xlsx，apply_barbour_supplier_overrides(dry_run=False)
        b) 清空 inventory
        c) 插入鲸芽已发布商品
        d) 写入 jingya_id 映射
        e) 单一最佳供货商回填 inventory
        f) 10% 价格带库存合并
"""

from config import BARBOUR
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import (
    generate_price_excels_bulk,
)
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.common.import_txt_to_products import (
    batch_import_txt_to_barbour_product,
)
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import (
    insert_jingyaid_to_db,
    clear_barbour_inventory,
    insert_missing_products_with_zero_stock,
)
from brands.barbour.common.build_supplier_jingya_mapping import (
    fill_supplier_map,
    apply_barbour_supplier_overrides,
    export_supplier_stock_price_report,
    reassign_low_stock_suppliers,
)
from brands.barbour.jingya.merge_offer_into_inventory import (
    backfill_barbour_inventory_single_supplier,
    merge_band_stock_into_inventory,
    apply_fixed_prices_from_excel,
)

# 配置文件路径（你可以按需要改到 config.py 里去）
EXCLUDE_LIST_XLSX = r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
SUPPLIER_OVERRIDE_XLSX = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"


# ============= 通用小工具函数 =============


def _rebuild_inventory_from_jingya(merge_band: bool = True):
    """
    通用：清空 inventory -> 重新插入鲸芽已发布商品 -> 写入 jingya_id -> 回填价格和库存。
    - 回填价格：单一最佳供货商（barbour_supplier_map）
    - 回填库存：如果 merge_band=True，则额外执行 10% 价格带库存合并
    """
    print(">>> 清空 barbour_inventory...")
    clear_barbour_inventory()

    print(">>> 插入鲸芽已发布商品（缺失记录）...")
    insert_missing_products_with_zero_stock("barbour")

    print(">>> 写入 Jingya ID 映射到 barbour_inventory...")
    insert_jingyaid_to_db("barbour")

    print(">>> 根据 barbour_supplier_map 用单一供货商回填价格 + 主库存...")
    backfill_barbour_inventory_single_supplier()

    if merge_band:
        print(">>> 按 10% 价格带合并多站点库存（只影响 stock_count，不动价格）...")
        merge_band_stock_into_inventory(band_ratio=0.10)

    apply_fixed_prices_from_excel(
    code_col="商品编码",
    sheet_name=0,
    xlsx_path=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx",
    dry_run=False
    )
    print(">>> barbour_inventory 回填完成。")


# ============= 各种典型场景 =============


def scenario_full_rebuild():
    """
    场景1：数据库数据已在（barbour_products, barbour_offers 已导入），
           需要完全重建 supplier_map + inventory。

    注意：与 after_new_publish 同理，必须先重建 inventory 骨架（让 is_published=TRUE 写入 DB），
          再调用 fill_supplier_map，否则在全新数据库或 inventory 被清空的情况下，
          fill_supplier_map 读到的 published 集合为空，所有商品都拿不到供货商（静默失败）。
    """
    print("=== 场景1：Full rebuild（重建 supplier_map + inventory）===")

    # 1) 先重建 inventory 骨架：清空 → 插入所有已发布商品 → 写入 jingya_id / is_published=TRUE
    print(">>> 清空 barbour_inventory...")
    clear_barbour_inventory()

    print(">>> 插入鲸芽已发布商品（is_published=FALSE 占位）...")
    insert_missing_products_with_zero_stock("barbour")

    print(">>> 写入 Jingya ID 映射，将已发布商品标记 is_published=TRUE...")
    insert_jingyaid_to_db("barbour")

    # 2) 此时 inventory 里所有已发布商品已有 is_published=TRUE，再强制重算 supplier_map
    print(">>> 强制重算 barbour_supplier_map（force_refresh=True）...")
    fill_supplier_map(
        force_refresh=True,
        exclude_xlsx=EXCLUDE_LIST_XLSX,
    )

    # 3) 根据新的 supplier_map 回填价格 + 库存
    print(">>> 根据 barbour_supplier_map 用单一供货商回填价格 + 主库存...")
    backfill_barbour_inventory_single_supplier()

    print(">>> 按 10% 价格带合并多站点库存（只影响 stock_count，不动价格）...")
    merge_band_stock_into_inventory(band_ratio=0.10)

    apply_fixed_prices_from_excel(
        code_col="商品编码",
        sheet_name=0,
        xlsx_path=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx",
        dry_run=False
    )
    print(">>> barbour_inventory 回填完成。")


def scenario_refresh_inventory():
    """
    场景2：supplier_map 已有，只是 offers 信息更新了，
           需要基于现有 map 重算 inventory。
    """
    print("=== 场景2：仅刷新 inventory（不改 supplier_map）===")
    _rebuild_inventory_from_jingya(merge_band=True)


def scenario_after_new_publish():
    """
    场景3：鲸芽发布了新商品，只需要：
           - 为【新商品】建立 supplier_map
           - 并重新生成所有商品的 inventory

    注意：必须先重建 inventory（让新品的 is_published=TRUE 写入 DB），
          再调用 fill_supplier_map，否则新品在 barbour_inventory 里还不存在，
          fill_supplier_map 读 WHERE is_published=TRUE 时会漏掉新品，导致无法分配供货商。
    """
    print("=== 场景3：鲸芽发布新品后，增量填充 supplier_map + 重建 inventory ===")

    # 1) 先重建 inventory 骨架：清空 → 插入所有已发布商品 → 写入 jingya_id / is_published=TRUE
    print(">>> 清空 barbour_inventory...")
    clear_barbour_inventory()

    print(">>> 插入鲸芽已发布商品（包含新上的，is_published=FALSE 占位）...")
    insert_missing_products_with_zero_stock("barbour")

    print(">>> 写入 Jingya ID 映射，将已发布商品标记 is_published=TRUE...")
    insert_jingyaid_to_db("barbour")

    # 2) 此时 barbour_inventory 中新品已有 is_published=TRUE，再填 supplier_map
    print(">>> 为 null supplier 的商品补充供应商映射（force_refresh=False）...")
    fill_supplier_map(
        force_refresh=False,
        exclude_xlsx=EXCLUDE_LIST_XLSX,
    )

    # 3) 根据最新的 supplier_map 回填价格 + 库存（跳过 clear/insert/jingyaid，直接从回填开始）
    print(">>> 根据 barbour_supplier_map 用单一供货商回填价格 + 主库存...")
    backfill_barbour_inventory_single_supplier()

    print(">>> 按 10% 价格带合并多站点库存（只影响 stock_count，不动价格）...")
    merge_band_stock_into_inventory(band_ratio=0.10)

    apply_fixed_prices_from_excel(
        code_col="商品编码",
        sheet_name=0,
        xlsx_path=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx",
        dry_run=False
    )
    print(">>> barbour_inventory 回填完成。")


def scenario_reassign_low_stock_preview():
    """
    场景4（预览版）：仅预览低库存商品的“换供应商”建议，不改数据库。
    """
    print("=== 场景4：预览低库存商品的换供应商建议（dry_run=True）===")

    reassign_low_stock_suppliers(
        size_threshold=3,
        dry_run=True,
        # 如果希望跳过某些编码，可以打开下面这一行：
        # exclude_xlsx=EXCLUDE_LIST_XLSX,
    )

    print(">>> 上述输出为建议列表，仅打印，不改 supplier_map / inventory。")


def scenario_reassign_low_stock_apply():
    """
    场景5（实战版）：对低库存商品实际执行换供应商，并重建 inventory。
    """
    print("=== 场景5：应用低库存商品换供应商，并重建 inventory ===")

    # 1) 真的更新 supplier_map
    print(">>> 更新 barbour_supplier_map（dry_run=False）...")
    reassign_low_stock_suppliers(
        size_threshold=3,
        dry_run=False,
        # 建议真更新时，最好配置排除清单：
        exclude_xlsx=EXCLUDE_LIST_XLSX,
    )

    # 2) 更新 supplier_map 后，重新回填 inventory
    _rebuild_inventory_from_jingya(merge_band=True)


def scenario_supplier_overrides():
    """
    场景6：手工 Excel 覆盖重点商品供应商，并重建 inventory。
    """
    print("=== 场景6：按 barbour_supplier.xlsx 覆盖重点商品供应商，并重建 inventory ===")

    print(f">>> 应用手工供应商覆盖：{SUPPLIER_OVERRIDE_XLSX}")
    # 先 dry_run 看看有没有语法问题 / 意外行
    apply_barbour_supplier_overrides(SUPPLIER_OVERRIDE_XLSX, dry_run=True)
    # 确认无误后再真正执行
    apply_barbour_supplier_overrides(SUPPLIER_OVERRIDE_XLSX, dry_run=False)

    # 覆盖 supplier_map 后，重新回填 inventory
    _rebuild_inventory_from_jingya(merge_band=True)


# ============= 总控入口 =============


def barbour_database_import_pipeline(mode: str = "refresh_inventory"):
    """
    总控入口：
    mode 可选：
      - "full_rebuild"
      - "refresh_inventory"
      - "after_new_publish"
      - "reassign_low_stock_preview"
      - "reassign_low_stock_apply"
      - "supplier_overrides"
    """
    if mode == "full_rebuild":
        scenario_full_rebuild()
    elif mode == "refresh_inventory":
        scenario_refresh_inventory()
    elif mode == "after_new_publish":
        scenario_after_new_publish()
    elif mode == "reassign_low_stock_preview":
        scenario_reassign_low_stock_preview()
    elif mode == "reassign_low_stock_apply":
        scenario_reassign_low_stock_apply()
    elif mode == "supplier_overrides":
        scenario_supplier_overrides()
    else:
        raise ValueError(f"未知 mode: {mode}")


if __name__ == "__main__":
    # TODO：按需要修改这里的默认模式
    # 例如：
    #   - 初次重建：mode = "full_rebuild"
    #   - 日常更新库存：mode = "refresh_inventory"
    #   - 新品发布：mode = "after_new_publish"
    #   - 检查低库存换供应商建议：mode = "reassign_low_stock_preview"
    #   - 真正执行低库存换供应商：mode = "reassign_low_stock_apply"
    #   - 用 Excel 强制覆盖供应商：mode = "supplier_overrides"

    barbour_database_import_pipeline(mode="after_new_publish")
