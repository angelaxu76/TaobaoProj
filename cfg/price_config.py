# cfg/price_config.py
#
# 唯一价格配置入口 —— 所有价格相关参数只在这里修改
#
# 结构：
#   全局参数         → EXCHANGE_RATE, DEFAULT_DELIVERY, DEFAULT_UNTAXED_MARGIN, DEFAULT_RETAIL_MARGIN
#   品牌定价策略     → BRAND_STRATEGY
#   品牌折扣率       → BRAND_DISCOUNT
#   品牌参数覆盖     → BRAND_PRICE_OVERRIDES（不填则用默认值）
#   低价补偿         → LOW_PRICE_BUMPS


# ── 全局参数 ──────────────────────────────────────────────────────────────────
EXCHANGE_RATE          = 9.4    # 英镑 → 人民币，所有品牌共用
DEFAULT_DELIVERY       = 7      # 默认运费（英镑）
DEFAULT_UNTAXED_MARGIN = 1.15   # 未税加成系数（精雅渠道）
DEFAULT_RETAIL_MARGIN  = 1.35   # 零售价加成（淘宝店铺价 = 未税价 × 此系数）


# ── 品牌定价策略 ───────────────────────────────────────────────────────────────
# 决定"用哪个 GBP 价做 base"，策略实现见 channels/jingya/pricing/discount_strategies_v2.py
#
# 可选值：
#   min_price_times_ratio           取 min(原价, 折扣价) × 折扣率（最激进压价）
#   discount_or_original_ratio      折扣价 vs (原价 × 折扣率) 取低（平衡）
#   discount_priority               有折扣价就直接用，否则原价 × 折扣率（尊重官网折扣）
#   ladder_wrap_min_price_times_ratio       阶梯抬价后再走 min_price 策略
#   ladder_wrap_discount_or_original_ratio  阶梯抬价后再走 discount_or_original 策略
#   ladder_wrap_discount_priority           阶梯抬价后再走 discount_priority 策略
BRAND_STRATEGY = {
    "camper": "min_price_times_ratio",
    "ecco":   "discount_priority",
    "geox":   "discount_priority",
    "clarks": "discount_priority",
}


# ── 品牌折扣率 ─────────────────────────────────────────────────────────────────
# base_price 的最终乘数；不配置的品牌默认 1.0（不打折）
BRAND_DISCOUNT = {
    "camper": 0.75,   # ~75折
    "ecco":   0.85,   # ~85折（部分策略下生效）
    "geox":   1.00,
    "clarks": 1.00,
    "barbour": 1.00,
}


# ── 品牌级参数覆盖 ─────────────────────────────────────────────────────────────
# 不填则使用上方 DEFAULT_* 全局默认值
# 可覆盖字段：delivery（运费）、untaxed_margin、retail_margin
BRAND_PRICE_OVERRIDES: dict = {
    # 示例：
    # "ecco": {"delivery": 8, "untaxed_margin": 1.15},
}


# ── 低价补偿 ───────────────────────────────────────────────────────────────────
# 格式：[(上限阈值, 补偿金额)]，按顺序匹配，命中即停止
# 含义：base_price < threshold → base_price += bump
LOW_PRICE_BUMPS = [
    (30, 9),   # base < 30 英镑 → +7
    (40, 7),   # base < 40 英镑 → +5
]
