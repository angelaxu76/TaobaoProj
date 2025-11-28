# brands/barbour/core/supplier_price_rules.py

from typing import Optional


def _to_f(v: Optional[float]) -> Optional[float]:
    """安全地把输入转成 float，None / 空字符串 会变成 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def strategy_all_ratio(
    original_price: Optional[float],
    discounted_price: Optional[float],
    extra_ratio: float,
    shipping_fee: float,
) -> float:
    """
    策略 1（升级版）：
    所有商品无论是否已经打折，都在“网页有效价”的基础上再乘以额外折扣率 extra_ratio，
    最后加上网站运费 shipping_fee。

    规则：
    1. “网页有效价” base_before 的选择逻辑：
       - 若 discounted_price > 0 → 使用 discounted_price
       - 否则若 original_price > 0 → 使用 original_price
       - 否则 → 返回 0.0（无有效价格）

    2. base_after_ratio = base_before × extra_ratio

    3. 最终价 = base_after_ratio + shipping_fee

    全程过滤 0 和非法值，保留两位小数。
    """

    # 转 float
    op = _to_f(original_price)
    dp = _to_f(discounted_price)

    # 过滤无效值（0 或负数）
    if op is not None and op <= 0:
        op = None
    if dp is not None and dp <= 0:
        dp = None

    # 1）确定网页基础价
    if dp is not None:
        base_before = dp
    elif op is not None:
        base_before = op
    else:
        return 0.0

    # 2）乘以额外折扣率
    try:
        r = float(extra_ratio)
    except (TypeError, ValueError):
        r = 1.0

    base_after_ratio = round(base_before * r, 2)

    # 3）加运费
    try:
        shipping = float(shipping_fee) if shipping_fee is not None else 0.0
    except (TypeError, ValueError):
        shipping = 0.0

    final_price = round(base_after_ratio + shipping, 2)
    return final_price

def strategy_ratio_when_no_discount(
    original_price: Optional[float],
    discounted_price: Optional[float],
    extra_ratio: float,
    shipping_fee: float,
) -> float:
    """
    有折扣就用折扣价（不叠加额外折扣）；
    没折扣时，对原价按 extra_ratio 打折；
    最后加上 shipping_fee。
    """

    op = _to_f(original_price)
    dp = _to_f(discounted_price)

    # 过滤无效数据
    if op is not None and op <= 0:
        op = None
    if dp is not None and dp <= 0:
        dp = None

    # 1) 先决定基础价
    if dp is not None:
        # 有折扣价 → 直接用折扣价，不再乘 extra_ratio
        base_after_ratio = round(dp, 2)
    elif op is not None:
        # 没折扣价 → 原价 * extra_ratio
        try:
            ratio = float(extra_ratio)
        except (TypeError, ValueError):
            ratio = 1.0
        base_after_ratio = round(op * ratio, 2)
    else:
        return 0.0

    # 2) 加运费
    try:
        shipping = float(shipping_fee) if shipping_fee is not None else 0.0
    except (TypeError, ValueError):
        shipping = 0.0

    final_price = round(base_after_ratio + shipping, 2)
    return final_price
