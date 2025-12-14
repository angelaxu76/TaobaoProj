# channels/jingya/pricing/discount_ladder_config.py
from __future__ import annotations
from typing import Dict, List, Tuple

# 阶梯：[(实际折扣阈值, 目标折扣率)]，按从大到小
DEFAULT_DISCOUNT_LADDER: List[Tuple[float, float]] = [
    (0.49, 0.43),  # 实际>=50% off -> 按 40% off 定价
    (0.39, 0.35),  # 实际>=40% off -> 按 30% off 定价
    (0.29, 0.25),  # 实际>=30% off -> 按 25% off 定价
]

# 实际折扣低于该阈值，不做“抬价”，直接用官网折扣价 d
DEFAULT_MIN_APPLY_DISCOUNT: float = 0.20

# 可选：按品牌覆盖
BRAND_DISCOUNT_LADDER: Dict[str, List[Tuple[float, float]]] = {}

# 可选：按品牌覆盖 min_apply
BRAND_MIN_APPLY_DISCOUNT: Dict[str, float] = {}

# 可选：极端折扣保护（防抓错/bug价）
# 如果 disc >= 0.80（80% off）默认不抬价，直接用 d（你也可以改成直接返回 d 或者直接返回 o*(1-目标折扣)）
DEFAULT_MAX_REASONABLE_DISCOUNT: float = 0.80
BRAND_MAX_REASONABLE_DISCOUNT: Dict[str, float] = {}
