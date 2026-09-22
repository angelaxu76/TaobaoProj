# -*- coding: utf-8 -*-
"""
allocate_and_sync() 专属配置——已迁移至
brands/barbour/pipeline/session_config.py 统一维护（跟 prepare_jingya_listing.py
的阶段开关、路径、供应商列表放在一起改）。

这里只保留同名转发导入，兼容 allocate_supplier_and_price.py /
tool_inspect_supplier.py 已有的 import 路径；不要在这个文件里改值。
"""

from brands.barbour.pipeline.session_config import (
    SUPPLIER_PRICE_TOLERANCE_PCT,
    SUPPLIER_MAX_SITES,
    SUPPLIER_MIN_SIZES_IN_STOCK,
    TAOBAO_STORE_DISCOUNT,
    SUPPLIER_OVERRIDE_XLSX,
)

__all__ = [
    "SUPPLIER_PRICE_TOLERANCE_PCT",
    "SUPPLIER_MAX_SITES",
    "SUPPLIER_MIN_SIZES_IN_STOCK",
    "TAOBAO_STORE_DISCOUNT",
    "SUPPLIER_OVERRIDE_XLSX",
]
