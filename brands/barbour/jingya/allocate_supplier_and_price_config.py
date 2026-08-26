# -*- coding: utf-8 -*-
"""
allocate_and_sync() 专属配置——供应商组合策略 / 定价折扣 / 人工干预 Excel 路径。

这几个参数原来分散在两处：
  - SUPPLIER_MIN_SIZES / SUPPLIER_MAX_SITES / TAOBAO_STORE_DISCOUNT
    混在 cfg/brands/barbour.py 里（那个文件另外还有约 300 行图片路径、
    颜色映射、编码前缀规则等和供应商/定价完全无关的配置）。
  - SUPPLIER_OVERRIDE_XLSX（人工指定供应商）此前只在已废弃的
    db_build_supplier_map_and_inventory.py 里硬编码，没有任何地方在用。
现在集中到这里，跟着 allocate_supplier_and_price.py 一起改，不用再去
cfg/brands/barbour.py 里翻。

注意：EXCLUDE_LIST_XLSX（排除清单）不在这里——它同时被 D 阶段的价格/
库存导出复用，属于整条流水线共用的路径，仍在 prepare_jingya_listing.py
的 CONFIG 区域维护。
"""

# ── 供应商组合策略 ──────────────────────────────────────────────
# 库存并集要覆盖到几个有货尺码才算"够用"（够用就停止追加供应商）
SUPPLIER_MIN_SIZES = 2
# 最多合并几家供应商来覆盖库存
SUPPLIER_MAX_SITES = 3

# ── 定价 ────────────────────────────────────────────────────────
# 未税价 -> 淘宝店铺价的折扣系数（1.0 = 不打折）
TAOBAO_STORE_DISCOUNT = 1.0

# ── 人工指定供应商（可选） ─────────────────────────────────────────
# Excel 需含列：商品编码 / 供货商。命中的商品跳过自动选择，
# 直接用指定站点，但仍走同一套定价/库存回填逻辑。
# 文件不存在时会被自动忽略，不影响正常运行。
SUPPLIER_OVERRIDE_XLSX = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"
