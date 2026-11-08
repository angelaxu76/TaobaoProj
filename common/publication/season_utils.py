# -*- coding: utf-8 -*-
"""
发布 Excel 的「上市年份季节」字段：取当前季节的下一个季节。

季节划分：春 3-5 月、夏 6-8 月、秋 9-11 月、冬 12-2 月
示例：
    2026-11 (秋) → 2026年冬季
    2026-12 (冬) → 2027年春季
    2027-01 (冬) → 2027年春季
    2026-07 (夏) → 2026年秋季
"""
from datetime import date


def get_next_season_label(today: date | None = None) -> str:
    d = today or date.today()
    y, m = d.year, d.month
    if 3 <= m <= 5:
        return f"{y}年夏季"
    if 6 <= m <= 8:
        return f"{y}年秋季"
    if 9 <= m <= 11:
        return f"{y}年冬季"
    # 冬季：12 月 → 次年春；1-2 月 → 当年春
    return f"{y + 1 if m == 12 else y}年春季"
