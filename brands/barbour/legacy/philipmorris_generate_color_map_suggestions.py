# -*- coding: utf-8 -*-
"""
根据 TXT.problem / unknown_colors.csv 自动生成
color_map_suggestions.txt（仅人工确认用）
"""

from pathlib import Path
from config import BARBOUR

BASE_DIR = Path(BARBOUR["TXT_DIRS"]["philipmorris"]).parent
UNKNOWN_COLOR_FILE = BASE_DIR / "unknown_colors.csv"
PROBLEM_SUMMARY_FILE = BASE_DIR / "problem_summary.csv"
OUTPUT_FILE = BASE_DIR / "color_map_suggestions.txt"

COLOR_MAP = BARBOUR["BARBOUR_COLOR_CODE_MAP"]


def load_file(path):
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            p = [v.strip() for v in line.split(",")]
            if len(p) >= 2:
                rows.append(p)
    return rows


def generate_suggestions():
    unknown = load_file(UNKNOWN_COLOR_FILE)
    prob = load_file(PROBLEM_SUMMARY_FILE)

    colors = set()

    for row in unknown:
        _, color, *_ = row
        colors.add(color.strip())

    for row in prob:
        _, color, _, reason, *_ = row
        if reason == "unknown_color":
            colors.add(color.strip())

    existing = {v["en"].lower() for v in COLOR_MAP.values()}
    new = [c for c in colors if c.lower() not in existing]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# 建议补充到 BARBOUR_COLOR_CODE_MAP（请人工确认）\n\n")
        for c in sorted(new):
            out.write(f'"XX": {{"en": "{c}", "zh": ""}},\n')

    print(f"✅ 已生成颜色建议：{OUTPUT_FILE}")


if __name__ == "__main__":
    generate_suggestions()
