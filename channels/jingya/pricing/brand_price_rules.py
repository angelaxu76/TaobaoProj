"""
品牌基准价计算规则（主要服务于鲸芽渠道的定价）

重要设计原则：
- 所有“默认折扣系数”只从 config.BRAND_DISCOUNT 中读取（在 discount_strategies 里使用）
- 本文件不再写死每个品牌的计算逻辑，只负责：
    品牌名 -> 策略名 (config.BRAND_STRATEGY)
          -> 策略函数 (discount_strategies.STRATEGY_MAP)
          -> 计算基础价格
- 不同品牌切换策略时，只需要修改 config.BRAND_STRATEGY
"""

from typing import Tuple

from config import BRAND_STRATEGY  # 品牌 -> 策略名
from channels.jingya.pricing.discount_strategies_v2 import STRATEGY_MAP  # 策略名 -> 策略函数


def _safe_float(x) -> float:
    """安全地把任意值转成 float，异常或 NaN/Inf 时返回 0.0"""
    try:
        v = float(x)
        if v != v or v == float("inf") or v == float("-inf"):
            return 0.0
        return v
    except Exception:
        return 0.0


def _compute_raw_price(original_gbp, discount_gbp) -> Tuple[float, float, float]:
    """
    计算“原始基础价”和原价/折后价的浮点数表示。

    返回:
      - raw: 不考虑品牌规则时的基础价，一般为 min(original, discount)
      - o: 原价 original_price_gbp（float）
      - d: 折后价 discount_price_gbp（float）
    """
    o = _safe_float(original_gbp)
    d = _safe_float(discount_gbp)

    if o > 0 and d > 0:
        raw = min(o, d)
    else:
        # 只有一个价格有效时，退而求其次
        raw = d if d > 0 else o

    return raw, o, d


def compute_brand_base_price(brand: str, original_gbp, discount_gbp) -> float:
    """
    根据品牌 + 原价/折扣价，计算“用于鲸芽价格计算”的 base price（单位 GBP）。

    说明：
    - 对外接口保持不变：compute_brand_base_price(brand, original_gbp, discount_gbp)
    - 内部通过 BRAND_STRATEGY + STRATEGY_MAP 决定最终使用哪个策略函数
    - 当前你配置的是：
        camper        -> min_price_times_ratio
        ecco          -> discount_priority
        geox          -> discount_priority
        clarks_jingya -> min_price_times_ratio
      这些都在 config.BRAND_STRATEGY 中定义。
    """
    brand = (brand or "").lower().strip()

    # 先算出 o / d / raw，方便未来有策略要用 raw 的时候扩展
    raw, o, d = _compute_raw_price(original_gbp, discount_gbp)

    # 1) 找到该品牌对应的策略名；默认使用 "min_price_times_ratio"
    strategy_name = BRAND_STRATEGY.get(brand, "min_price_times_ratio")

    # 2) 从策略映射中取出对应的策略函数
    strategy_func = STRATEGY_MAP.get(strategy_name)
    if strategy_func is None:
        raise ValueError(f"未知策略名称：{strategy_name}（brand={brand}）")

    # 3) 调用策略函数进行计算
    #    当前所有策略函数签名为 strategy(o, d, brand)
    return strategy_func(o, d, brand)
