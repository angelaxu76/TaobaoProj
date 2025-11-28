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
    策略：ratio_when_no_discount

    语义（改进版，考虑 dp == op / dp=0 等情况）：
    - 若 op 和 dp 同时存在：
        * 若 dp < op  => 视为“真的打折了”，直接用 dp（不再额外打折）
        * 若 dp >= op => 视为“没打折”，忽略 dp，用 op * extra_ratio
    - 若只有 dp（op 为空）：
        * 视为“网站给的有效售价”，直接用 dp（不再额外打折）
    - 若只有 op（dp 为空或为 0）：
        * 视为“没打折”，用 op * extra_ratio
    - 最后统一加 shipping_fee
    """

    op = _to_f(original_price)
    dp = _to_f(discounted_price)

    # 过滤无效数值（<=0 当作没有）
    if op is not None and op <= 0:
        op = None
    if dp is not None and dp <= 0:
        dp = None

    # 1) 先算折扣前/后的基准价 base_after_ratio
    if op is not None and dp is not None:
        # 两个都有：比较大小判断是不是“真打折”
        if dp < op:
            # 确认是打折价 -> 不叠加 extra_ratio
            base_after_ratio = round(dp, 2)
        else:
            # dp >= op -> 说明没有实际折扣（或者展示价=原价）
            # 忽略 dp，当成未打折价，给原价额外折扣
            try:
                r = float(extra_ratio)
            except (TypeError, ValueError):
                r = 1.0
            base_after_ratio = round(op * r, 2)

    elif dp is not None and op is None:
        # 只有一个 dp：不知道是否打折，保守：视作最终售价，不再叠加 extra_ratio
        base_after_ratio = round(dp, 2)

    elif op is not None and dp is None:
        # 只有原价：肯定没打折，对原价按 extra_ratio 打折
        try:
            r = float(extra_ratio)
        except (TypeError, ValueError):
            r = 1.0
        base_after_ratio = round(op * r, 2)

    else:
        # 两个都没有
        return 0.0

    # 2) 加运费
    try:
        shipping = float(shipping_fee) if shipping_fee is not None else 0.0
    except (TypeError, ValueError):
        shipping = 0.0

    final_price = round(base_after_ratio + shipping, 2)
    return final_price
