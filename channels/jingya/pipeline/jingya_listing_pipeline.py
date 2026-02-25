# -*- coding: utf-8 -*-
"""
鲸芽上架 Pipeline 共享步骤库

各品牌的 brands/[brand]/pipeline/prepare_jingya_listing.py 都调用这里的函数，
只需传入品牌名称字符串，具体抓取函数由品牌侧注入（fetch_fn）。

标准 Pipeline 步骤（按顺序）：
  Step 1  清空 TXT + 发布目录
  Step 2  抓取商品链接（由品牌侧提供 link_fn）
  Step 3  抓取商品信息（由品牌侧提供 fetch_fn）
  Step 4  TXT 导入数据库
  Step 5  导入鲸芽渠道绑定 ID（insert_jingyaid_to_db）
  Step 6  补零库存（已下架商品）
  Step 7  低库存自动下架
  Step 8  导出库存更新 Excel
  Step 9  导出价格更新 Excel
  Step 10 生成新品上架模板
  Step 11 生成低库存清单
  Step 12 生成淘宝店铺价格文件
"""

from config import BRAND_CONFIG

from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.ingest.import_channel_info import (
    insert_jingyaid_to_db,
    insert_missing_products_with_zero_stock,
)
from channels.jingya.maintenance.disable_low_stock_products import disable_low_stock_products
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_for_brand
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from channels.jingya.export.generate_publication_excel import generate_publication_excels
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand


def step_backup_and_clear(brand: str):
    """Step 1：清空 TXT + 发布目录（保留图片）"""
    cfg = BRAND_CONFIG[brand]
    backup_and_clear_brand_dirs(cfg)


def step_import_txt_to_db(brand: str, exchange_rate: float = 9.5, delivery_cost: float = 7,
                           untaxed_margin: float = 1.1, retail_margin: float = 1.43):
    """Step 4：TXT 导入数据库（鲸芽专用定价结构）"""
    import_txt_to_db_supplier(brand, exchange_rate=exchange_rate,
                               delivery_cost=delivery_cost,
                               untaxed_margin=untaxed_margin,
                               retail_margin=retail_margin)


def step_insert_jingya_ids(brand: str):
    """Step 5：解析鲸芽导出 Excel，写入渠道商品ID / SKUID 绑定关系"""
    insert_jingyaid_to_db(brand)


def step_zero_missing_stock(brand: str):
    """Step 6：将鲸芽存在但 TXT 中缺失的商品库存补零（已下架商品）"""
    insert_missing_products_with_zero_stock(brand)


def step_disable_low_stock(brand: str):
    """Step 7：有货尺码 < 2 的商品全部库存清零并下架"""
    disable_low_stock_products(brand)


def step_export_stock_excel(brand: str, output_folder: str):
    """Step 8：导出鲸芽库存更新 Excel"""
    export_stock_excel(brand, output_folder)


def step_export_price_excel(brand: str, output_folder: str,
                             chunk_size: int = 300, exchange_rate: float = 9.4):
    """Step 9：导出鲸芽价格更新 Excel"""
    export_jiangya_channel_prices(brand, output_folder,
                                   chunk_size=chunk_size, exchange_rate=exchange_rate)


def step_generate_publication_excels(brand: str):
    """Step 10：为新品生成鲸芽上架模板 Excel"""
    generate_publication_excels(brand)


def step_export_low_stock_report(brand: str, threshold: int = 5):
    """Step 11：导出低库存商品清单（供人工决策下架）"""
    export_low_stock_for_brand(brand, threshold=threshold)


def step_generate_store_price_excels(brand: str, input_dir: str, output_dir: str,
                                      suffix: str = "_价格",
                                      drop_rows_without_price: bool = False,
                                      blacklist_excel_file: str = None):
    """Step 12：生成淘宝店铺价格导入文件"""
    generate_price_excels_bulk(
        brand=brand,
        input_dir=input_dir,
        output_dir=output_dir,
        suffix=suffix,
        drop_rows_without_price=drop_rows_without_price,
        blacklist_excel_file=blacklist_excel_file,
    )


def step_generate_missing_links(brand: str, output_file: str):
    """工具步骤：找出鲸芽有但 TXT 中缺失的商品，生成待抓链接文件"""
    generate_missing_links_for_brand(brand, output_file)
