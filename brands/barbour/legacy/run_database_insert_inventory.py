from config import BARBOUR
from common_taobao.publication.generate_taobao_store_price_for_import_excel import (
    generate_price_excels_bulk,
)
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.common.import_txt_to_products import (
    batch_import_txt_to_barbour_product,
)
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import (
    insert_jingyaid_to_db,
    clear_barbour_inventory,
    insert_missing_products_with_zero_stock,
)
from brands.barbour.common.build_supplier_jingya_mapping_v2 import (
    fill_supplier_map,
    BandStockStrategy,
    apply_barbour_supplier_overrides,
    export_supplier_stock_price_report,
    reassign_low_stock_suppliers,
)
from brands.barbour.jingya.merge_offer_into_inventory import (
    backfill_barbour_inventory_single_supplier,
    merge_band_stock_into_inventory,
)

# 配置文件路径（你可以按需要改到 config.py 里去）
EXCLUDE_LIST_XLSX = r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
SUPPLIER_OVERRIDE_XLSX = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"


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

    print(">>> 重新计算 barbour_supplier_map（force_refresh=True）...")
    # fill_supplier_map(
    #     force_refresh=True,
    #     exclude_xlsx=EXCLUDE_LIST_XLSX,
    # )
    fill_supplier_map(strategy=BandStockStrategy(min_sizes=3, band_ratio=0.20))

    print(">>> 根据 barbour_supplier_map 用单一供货商回填价格 + 主库存...")
    backfill_barbour_inventory_single_supplier()

    print(">>> 按 10% 价格带合并多站点库存（只影响 stock_count，不动价格）...")
    merge_band_stock_into_inventory(band_ratio=0.10)

    print(">>> barbour_inventory 回填完成。")


if __name__ == "__main__":
    _rebuild_inventory_from_jingya()


