# channels/jingya/pricing/discount_ladder_config.py

from typing import Dict, List, Tuple

# 阶梯：[(实际折扣阈值, 回收比例)]
# 含义：actual_discount >= threshold → 回收 clawback_ratio
DEFAULT_DISCOUNT_LADDER: List[Tuple[float, float]] = [
    (0.50, 0.10),  # >=50% off → 回收 10%
    (0.40, 0.08),  # >=40% off → 回收 8%
    (0.30, 0.05),  # >=30% off → 回收 5%
]

# 实际折扣低于该值，不做回收
DEFAULT_MIN_APPLY_DISCOUNT: float = 0.30

# 防极端 bug 价（可选）
DEFAULT_MAX_REASONABLE_DISCOUNT: float = 0.80

# 品牌级覆盖（保持不变）
BRAND_DISCOUNT_LADDER: Dict[str, List[Tuple[float, float]]] = {}
BRAND_MIN_APPLY_DISCOUNT: Dict[str, float] = {}
BRAND_MAX_REASONABLE_DISCOUNT: Dict[str, float] = {}
