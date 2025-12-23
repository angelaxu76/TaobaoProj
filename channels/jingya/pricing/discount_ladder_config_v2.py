# channels/jingya/pricing/discount_ladder_config.py

from typing import Dict, List, Tuple

# 阶梯：[(实际折扣阈值, 回收比例)]
# 含义：actual_discount >= threshold → 回收 clawback_ratio
DEFAULT_DISCOUNT_LADDER: List[Tuple[float, float]] = [
    (0.80, 0.60),  # >=80% off → 抬到 60% off（价格=0.40o）
    (0.70, 0.52),  # >=70% off → 抬到 52% off（价格=0.48o）
    (0.60, 0.47),  # >=60% off → 抬到 47% off（价格=0.53o）
    (0.50, 0.40),  # >=50% off → 抬到 40% off（价格=0.60o）
    (0.40, 0.30),  # >=40% off → 抬到 30% off（价格=0.70o）
    (0.30, 0.25),  # >=30% off → 抬到 25% off（价格=0.75o）
]


# 实际折扣低于该值，不做回收
DEFAULT_MIN_APPLY_DISCOUNT: float = 0.30

# 防极端 bug 价（可选）
DEFAULT_MAX_REASONABLE_DISCOUNT: float = 0.90

# 品牌级覆盖（保持不变）
BRAND_DISCOUNT_LADDER: Dict[str, List[Tuple[float, float]]] = {}
BRAND_MIN_APPLY_DISCOUNT: Dict[str, float] = {}
BRAND_MAX_REASONABLE_DISCOUNT: Dict[str, float] = {}
