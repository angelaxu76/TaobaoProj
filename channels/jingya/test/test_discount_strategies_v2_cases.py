# test/test_discount_strategies_v2_cases.py
# 用途：快速验证 6 个策略在各种边界输入下的输出是否符合预期

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# 这里按你的项目结构导入
# 如果你现在是 v2 文件：channels/jingya/pricing/discount_strategies_v2.py
# 就用下面这一行（推荐）
from channels.jingya.pricing.discount_strategies_v2 import STRATEGY_MAP

# 如果你当前还是老文件名（discount_strategies.py），改成：
from channels.jingya.pricing.discount_strategies import STRATEGY_MAP


def fmt(x: Any) -> str:
    if x is None:
        return "None"
    return str(x)


def run_cases(cases: List[Dict[str, Any]], strategies: List[str]) -> None:
    # 打印 header
    headers = ["Case", "brand", "o", "d"] + strategies
    col_width = 20

    def print_row(row: List[str]) -> None:
        print(" | ".join(s.ljust(col_width) for s in row))

    print_row(headers)
    print("-" * (len(headers) * (col_width + 3)))

    for i, c in enumerate(cases, start=1):
        brand = c["brand"]
        o = c["o"]
        d = c["d"]

        row = [f"#{i} {c['name']}", brand, fmt(o), fmt(d)]
        for sname in strategies:
            fn = STRATEGY_MAP[sname]
            try:
                val = fn(o, d, brand)
                row.append(f"{val:.4f}")
            except Exception as e:
                row.append(f"ERROR: {type(e).__name__}")
        print_row(row)


def main():
    # 6 个策略（和你 STRATEGY_MAP 一致）
    strategies = [
        "min_price_times_ratio",
        "discount_or_original_ratio",
        "discount_priority",
        "ladder_wrap_min_price_times_ratio",
        "ladder_wrap_discount_or_original_ratio",
        "ladder_wrap_discount_priority",
    ]

    # 测试用例设计说明：
    # - 覆盖 None / 字符串 / 货币符号 / d>o / o=0 / d=0 / 深折扣 / 阈值边界
    cases = [
        # 1) 正常场景：折扣很小（10% off），应该基本不触发阶梯抬价
        {"name": "normal 10% off", "brand": "camper", "o": 100, "d": 90},

        # 2) d=0：没有折扣价（或抓不到折扣价）
        {"name": "no discount price (d=0)", "brand": "camper", "o": 100, "d": 0},

        # 3) o=0：原价缺失（只抓到折扣价）
        {"name": "no original price (o=0)", "brand": "camper", "o": 0, "d": 90},

        # 4) 输入是字符串，含£符号（常见脏数据）
        {"name": "string with currency", "brand": "camper", "o": "£100", "d": "£90"},

        # 5) brand 大小写混用（验证 brand.lower() 容错）
        {"name": "brand case mix", "brand": "ECCO", "o": 100, "d": 90},

        # 6) d > o（抓取抖动：折扣价反而比原价高）
        {"name": "bad data d>o", "brand": "camper", "o": 100, "d": 120},

        # 7) 触发阶梯：50% off（d=50），阶梯应该抬到 40% off => 60
        {"name": "deep 50% off (ladder->40% off)", "brand": "camper", "o": 100, "d": 50},

        # 8) 触发阶梯：40% off（d=60），阶梯抬到 30% off => 70（因为 max(d, target)）
        {"name": "deep 40% off (ladder->30% off)", "brand": "camper", "o": 100, "d": 60},

        # 9) 触发阶梯：30% off（d=70），阶梯抬到 25% off => 75
        {"name": "deep 30% off (ladder->25% off)", "brand": "camper", "o": 100, "d": 70},

        # 10) 刚好低于 min_apply（默认 20%）：19% off => 不抬价
        {"name": "below min_apply 19% off (no ladder)", "brand": "camper", "o": 100, "d": 81},

        # 11) 极端折扣 90% off：如果你配置了 DEFAULT_MAX_REASONABLE_DISCOUNT=0.80，则应不抬价
        {"name": "extreme 90% off (should not ladder)", "brand": "camper", "o": 100, "d": 10},

        # 12) None 输入：确保不崩
        {"name": "None values", "brand": "camper", "o": None, "d": None},
    ]

    run_cases(cases, strategies)


if __name__ == "__main__":
    main()
