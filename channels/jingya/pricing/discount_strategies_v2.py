"""
折扣策略库 v2：
- 保留 v1 的三大策略函数（所有容错逻辑不动）
- 新增“阶梯折扣”计算：先把折扣价 d 修正为 d2（抬价）
- 新增三条 wrapper 策略：把 d2 带回原策略，保证稳
"""

from __future__ import annotations
from config import BRAND_DISCOUNT

# 阶梯配置（独立文件，方便找和改）
try:
    from channels.jingya.pricing.discount_ladder_config import (
        DEFAULT_DISCOUNT_LADDER,
        DEFAULT_MIN_APPLY_DISCOUNT,
        BRAND_DISCOUNT_LADDER,
        BRAND_MIN_APPLY_DISCOUNT,
        DEFAULT_MAX_REASONABLE_DISCOUNT,
        BRAND_MAX_REASONABLE_DISCOUNT,
    )
except Exception:
    # 如果你暂时没放这个文件，也不会炸：默认直接不启用阶梯抬价
    DEFAULT_DISCOUNT_LADDER = [(0.50, 0.40), (0.40, 0.30), (0.30, 0.25)]
    DEFAULT_MIN_APPLY_DISCOUNT = 0.20
    BRAND_DISCOUNT_LADDER = {}
    BRAND_MIN_APPLY_DISCOUNT = {}
    DEFAULT_MAX_REASONABLE_DISCOUNT = 0.80
    BRAND_MAX_REASONABLE_DISCOUNT = {}

from channels.jingya.pricing.discount_ladder_config_v2 import (
    DEFAULT_DISCOUNT_LADDER,
    DEFAULT_MIN_APPLY_DISCOUNT,
    DEFAULT_MAX_REASONABLE_DISCOUNT,
    BRAND_DISCOUNT_LADDER,
    BRAND_MIN_APPLY_DISCOUNT,
    BRAND_MAX_REASONABLE_DISCOUNT,
)


def strategy_ladder_clawback_ratio(o: float, d: float, brand: str) -> float:
    """
    阶梯回收型折扣策略：
    - 折扣 >= 阈值 → 回收固定比例
    - 折扣 < MIN_APPLY → 不处理
    """
    if o <= 0 or d <= 0:
        return max(o, d)

    actual_discount = 1 - d / o  # 例如 0.65

    # 极端折扣保护
    max_reasonable = BRAND_MAX_REASONABLE_DISCOUNT.get(
        brand, DEFAULT_MAX_REASONABLE_DISCOUNT
    )
    if actual_discount >= max_reasonable:
        return d

    min_apply = BRAND_MIN_APPLY_DISCOUNT.get(
        brand, DEFAULT_MIN_APPLY_DISCOUNT
    )
    if actual_discount < min_apply:
        return d

    ladder = BRAND_DISCOUNT_LADDER.get(
        brand, DEFAULT_DISCOUNT_LADDER
    )

    for threshold, clawback in ladder:
        if actual_discount >= threshold:
            final_discount = max(0.0, actual_discount - clawback)
            return o * (1 - final_discount)

    return d


def _to_float(x) -> float:
    """最大化兼容：None/空字符串/£xx 之类都尽量转成 float，失败返回 0.0"""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    try:
        s = str(x).strip()
        # 简单清洗：去掉货币符号和逗号
        s = s.replace("£", "").replace(",", "")
        return float(s) if s else 0.0
    except Exception:
        return 0.0


# =========================
# v1 原策略：保持不动（稳）
# =========================

def strategy_min_price_times_ratio(o, d, brand):
    """
    策略 1:
    - 如果 o 或 d 有一个是 0，则使用另一个
    - 如果两个都大于 0，取较小的
    - 最终乘以品牌额外折扣率 BRAND_DISCOUNT[brand]
    """

    # 转成 float，防止 None 或字符串
    o = _to_float(o)
    d = _to_float(d)


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
    brand_key = str(brand).lower()
    ratio = float(BRAND_DISCOUNT.get(brand_key, 1.0))


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
    o = _to_float(o)
    d = _to_float(d)


    try:
        d = float(d) if d is not None else 0.0
    except:
        d = 0.0

    brand_key = str(brand).lower()
    ratio = float(BRAND_DISCOUNT.get(brand_key, 1.0))


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
    o = _to_float(o)
    d = _to_float(d)


    try:
        d = float(d) if d is not None else 0.0
    except:
        d = 0.0

    brand_key = str(brand).lower()
    ratio = float(BRAND_DISCOUNT.get(brand_key, 1.0))


    # 如果有折扣价 → 直接用折扣价（优先级最高）
    if d > 0:
        return d

    # 否则用原价 × 比例
    return o * ratio

# =========================
# v2 新增：阶梯折扣价计算
# =========================

def get_ladder_discount_price(o, d, brand) -> float:
    """
    输入：原价 o、折扣价 d
    输出：阶梯修正后的折扣价 d2（用于“抬价”，不跟到底）

    规则（默认）：
    - disc = 1 - d/o
    - disc < min_apply => 不抬价，返回 d
    - disc >= 50% => 目标 40% off，即 o*(1-0.40)=0.60o
    - disc >= 40% => 目标 30% off，即 0.70o
    - disc >= 30% => 目标 25% off，即 0.75o
    - 返回 max(d, 目标价)（只抬价，不降价）

    保护：
    - o<=0 或 d<=0：返回原 d（交给旧策略兜底）
    - d>=o：返回原 d（避免抓取错误导致“折扣价高于原价”）
    - disc 过于离谱（默认>=80%）：返回原 d（避免 bug 价/抓错）
    """
    brand_key = str(brand).lower()
    o = _to_float(o)
    d = _to_float(d)

    if o <= 0 or d <= 0:
        return d
    if d >= o:
        return d

    disc = 1.0 - (d / o)

    min_apply = float(BRAND_MIN_APPLY_DISCOUNT.get(brand_key, DEFAULT_MIN_APPLY_DISCOUNT))
    if disc < min_apply:
        return d

    max_reasonable = float(BRAND_MAX_REASONABLE_DISCOUNT.get(brand_key, DEFAULT_MAX_REASONABLE_DISCOUNT))
    if disc >= max_reasonable:
        # 极端折扣：默认不抬价，直接返回 d，避免抓错时把价格抬到不合理
        return d

    ladder = BRAND_DISCOUNT_LADDER.get(brand_key, DEFAULT_DISCOUNT_LADDER)
    for actual_thr, target_disc in ladder:
        if disc >= float(actual_thr):
            target_price = o * (1.0 - float(target_disc))
            return max(d, target_price)

    return d


# =========================
# v2 新增：wrapper 策略（稳）
# =========================

def strategy_ladder_wrap_min_price_times_ratio(o, d, brand):
    d2 = get_ladder_discount_price(o, d, brand)
    return strategy_min_price_times_ratio(o, d2, brand)

def strategy_ladder_wrap_discount_or_original_ratio(o, d, brand):
    d2 = get_ladder_discount_price(o, d, brand)
    return strategy_discount_or_original_ratio(o, d2, brand)

def strategy_ladder_wrap_discount_priority(o, d, brand):
    d2 = get_ladder_discount_price(o, d, brand)
    return strategy_discount_priority(o, d2, brand)


# =========================
# 策略注册表
# =========================

# =========================
# 策略注册表（Price Strategy Map）
#
# 说明：
# - 所有策略的输入都是：原价 o、折扣价 d、品牌 brand
# - 所有策略的输出都是：一个 GBP 基准价（后续再做汇率/加成）
#
# v1 原始策略（不含阶梯，历史稳定版本）
#
# 1) min_price_times_ratio
#    - 先取原价 o 和折扣价 d 中的最低价
#    - 再乘以品牌折扣率（可能产生二次折扣）
#    - 用途：强力压价 / 冲销量（最激进）
#
# 2) discount_or_original_ratio
#    - 折扣价 d 与 (原价 o × 品牌折扣率) 取更低
#    - 不会对折扣价再叠加品牌折扣
#    - 用途：通用、安全、最平衡
#
# 3) discount_priority
#    - 只要有折扣价 d，就直接使用
#    - 只有在没有折扣价时，才用 o × 品牌折扣率
#    - 用途：尊重官网折扣价，价格稳定
#
# v2 阶梯 wrapper 策略（推荐）
# 特点：
# - 先根据“阶梯折扣规则”把异常深折扣抬回合理区间（d → d2）
# - 再调用对应的 v1 策略
# - 所有 v1 的防炸 / 容错逻辑完全保留
#
# 4) ladder_wrap_min_price_times_ratio
#    - 折扣价先阶梯抬价，再走最激进策略
#    - 用途：在压价的同时，避免极端低价
#
# 5) ladder_wrap_discount_or_original_ratio
#    - 折扣价先阶梯抬价，再做理性比较
#    - 用途：主力推荐，利润与销量最平衡
#
# 6) ladder_wrap_discount_priority
#    - 折扣价先阶梯抬价，抬完直接用
#    - 用途：价格可信、稳定，不叠加折扣
# =========================

STRATEGY_MAP = {
    # v1
    "min_price_times_ratio": strategy_min_price_times_ratio,
    "discount_or_original_ratio": strategy_discount_or_original_ratio,
    "discount_priority": strategy_discount_priority,
    "ladder_clawback_ratio": strategy_ladder_clawback_ratio,  # 👈 新增

    # v2 wrapper（先阶梯抬价，再走 v1）
    "ladder_wrap_min_price_times_ratio": strategy_ladder_wrap_min_price_times_ratio,
    "ladder_wrap_discount_or_original_ratio": strategy_ladder_wrap_discount_or_original_ratio,
    "ladder_wrap_discount_priority": strategy_ladder_wrap_discount_priority,
}
