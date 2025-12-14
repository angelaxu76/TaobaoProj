"""
折扣策略库：集中管理所有折扣策略逻辑
"""

from config import BRAND_DISCOUNT


def strategy_min_price_times_ratio(o, d, brand):
    """
    策略 1:
    - 如果 o 或 d 有一个是 0，则使用另一个
    - 如果两个都大于 0，取较小的
    - 最终乘以品牌额外折扣率 BRAND_DISCOUNT[brand]
    """

    # 转成 float，防止 None 或字符串
    try:
        o = float(o) if o is not None else 0.0
    except:
        o = 0.0

    try:
        d = float(d) if d is not None else 0.0
    except:
        d = 0.0

    # 1) 一个是 0，另一个不是
    if o == 0 and d != 0:
        base = d
    elif d == 0 and o != 0:
        base = o

    # 2) 都不为 0 → 取较小值
    elif o > 0 and d > 0:
        base = min(o, d)

    # 3) 都为 0 → 返回 0
    else:
        return 0.0

    # 额外折扣率（默认 1.0）
    ratio = float(BRAND_DISCOUNT.get(brand.lower(), 1.0))

    # 返回最终基准价
    return base * ratio

def strategy_discount_or_original_ratio(o, d, brand):
    """
    策略 2：
    - 如果折扣价 d == 0：返回 原价 * ratio
    - 如果原价 o == 0 且 d != 0：直接返回 d
    - 如果两个都 > 0：返回 min(d, o * ratio)
    """

    # 安全转换为 float
    try:
        o = float(o) if o is not None else 0.0
    except:
        o = 0.0

    try:
        d = float(d) if d is not None else 0.0
    except:
        d = 0.0

    ratio = float(BRAND_DISCOUNT.get(brand.lower(), 1.0))

    # 1) 折扣价不存在 → 原价 × ratio
    if d == 0:
        return o * ratio

    # 2) 原价不存在（极少发生，但必须处理）
    if o == 0:
        return d

    # 3) 两者都存在时 → 取更便宜的价格
    return min(d, o * ratio)

def strategy_discount_priority(o, d, brand):
    """
    策略 3：
    - 如果折扣价 d > 0：直接返回 d
    - 如果折扣价 d == 0：返回 原价 * ratio
    """

    # 安全 float 转换
    try:
        o = float(o) if o is not None else 0.0
    except:
        o = 0.0

    try:
        d = float(d) if d is not None else 0.0
    except:
        d = 0.0

    ratio = float(BRAND_DISCOUNT.get(brand.lower(), 1.0))

    # 如果有折扣价 → 直接用折扣价（优先级最高）
    if d > 0:
        return d

    # 否则用原价 × 比例
    return o * ratio

# 策略注册表（可不断添加新策略）
STRATEGY_MAP = {
    "min_price_times_ratio": strategy_min_price_times_ratio,
    "discount_or_original_ratio": strategy_discount_or_original_ratio,  # ← 新增这一行
    "discount_priority": strategy_discount_priority,   # ← 新增策略 3
}
