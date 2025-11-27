"""
品牌基准价计算规则（主要服务于鲸芽渠道的定价）

⚠️ 重要设计原则：
- 所有“默认折扣系数”只从 config.BRAND_DISCOUNT 中读取
- 本文件不硬编码 0.71 / 0.9 / 0.98 等具体数值
- 不同品牌只在这里定义逻辑，折扣数值统一在 config.py 维护
"""

from typing import Tuple
from config import BRAND_DISCOUNT  # 只作为折扣参数来源，不在这里写死数字


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
    - 所有品牌默认折扣只从 config.BRAND_DISCOUNT 读取；
    - 本函数只负责“逻辑规则”，不保存实际折扣数字；
    - 当 BRAND_DISCOUNT 中没有配置某品牌时，使用 1.0（即不额外打折）。
    """
    brand = (brand or "").lower().strip()
    raw, o, d = _compute_raw_price(original_gbp, discount_gbp)

    # ========== Camper 规则 ==========
    # 需求（你之前说明）：
    # - Camper 有一个“期望折扣” ratio_conf（例如 0.71），从 BRAND_DISCOUNT["camper"] 读取；
    # - 如果官网实际折扣比这个更狠（site_ratio < ratio_conf），则以 ratio_conf 为准：base = 原价 * ratio_conf；
    # - 如果官网折扣没那么狠（site_ratio >= ratio_conf），则按折后价 d 计算；
    # - 无法判断折扣时，用 raw * ratio_conf。
    if brand == "camper":
        extra_ratio = float(BRAND_DISCOUNT.get("camper", 1.0))

        o = _safe_float(original_gbp)
        d = _safe_float(discount_gbp)

        prices = []

        # 把有效价格加入列表（>0）
        if o > 0:
            prices.append(o)
        if d > 0:
            prices.append(d)

        if not prices:
            # 没有任何有效价格 → 返回 0
            return 0.0

        # 两者都有效 → 取较小的；只有一个有效 → 自动就是那一个
        base_raw = min(prices)

        # 再乘以 config 的折扣（0.75）
        return base_raw * extra_ratio


    # ========== ECCO 规则 ==========
    # 需求：
    # - 如果已经有折扣（d < o），那就直接用折后价 d，不再在 d 上 *0.9；
    # - 如果没有折扣（没有 d / d>=o / o==0），则对 raw 再打 BRAND_DISCOUNT["ecco"] 这一下。
    if brand == "ecco":
        ratio_conf = float(BRAND_DISCOUNT.get("ecco", 1.0))

        if o > 0 and d > 0 and d < o:
            # 官网已经打折 → 用折后价
            return d
        else:
            # 没有明显折扣 → 对基础价再应用 ecco 品牌折扣
            return raw * ratio_conf

    # ========== GEOX 规则（当前版本，可后续调整） ==========
    # 建议规则：
    # - 如果有折扣（d < o）：用折后价 d；
    # - 如果无折扣：对 raw 应用 BRAND_DISCOUNT["geox"]。
    if brand == "geox":
        ratio_conf = float(BRAND_DISCOUNT.get("geox", 1.0))

        if o > 0 and d > 0 and d < o:
            return d
        else:
            return raw * ratio_conf

    # ========== Clarks Jingya 规则 ==========
    # 需求：
    # - 不做品牌额外折扣，只取 min(o, d) 作为基础价。
    if brand == "clarks_jingya":
        if o > 0 and d > 0:
            return min(o, d)
        else:
            return raw

    # ========== 其它品牌通用规则 ==========
    # - 先算 raw = min(o, d)；
    # - 再看 BRAND_DISCOUNT 中有没有对应折扣，有则乘一下；
    # - 没有配置时，默认 1.0（即不折扣）。
    ratio_conf = float(BRAND_DISCOUNT.get(brand, 1.0))
    return raw * ratio_conf
