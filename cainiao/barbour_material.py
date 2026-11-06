# -*- coding: utf-8 -*-
"""
从 Barbour 商品描述中提取外层面料成分，用于海关备案的 "主要成分"。

描述写法不统一，且常混有里料/绒球成分，例如：
  Main Outer: 100% Acrylic; Faux Fur Trim: 74% Acrylic, 16% Modacrylic, 10% Polyester
  Outer: 100% Cotton (Waxed); Lining: 100% Cotton
  65% polyester, 20% wool, 10% acrylic, 5% polyamide
只采用比例合计 100% 的一组，并跳过里料/装饰部分；提取不到时返回 ""。
"""
import re
from typing import Iterable, List, Tuple

FIBER_ZH = {
    "modacrylic": "改性腈纶",
    "acrylic": "腈纶",
    "polyester": "涤纶",
    "polyamide": "锦纶",
    "nylon": "锦纶",
    "cotton": "棉",
    "lambswool": "羊毛",
    "wool": "羊毛",
    "cashmere": "羊绒",
    "viscose": "粘胶纤维",
    "elastane": "氨纶",
    "spandex": "氨纶",
    "silk": "蚕丝",
    "linen": "亚麻",
    "alpaca": "羊驼毛",
    "mohair": "马海毛",
    "acetate": "醋酸纤维",
}

_FIBERS = "|".join(sorted(FIBER_ZH, key=len, reverse=True))
_ITEM = re.compile(
    rf"(\d{{1,3}})\s*%\s*"
    rf"(?:(?:waterproof|waxed|recycled|pure|organic|soft|british|merino|virgin)\s+)*"
    rf"({_FIBERS})\b(?:\s*\([^)]*\))?",
    re.I,
)
_JOINER = re.compile(r"(?:\s|,|/|&|and)*", re.I)
_OUTER_LABEL = re.compile(r"\b(outer|main|shell)\b", re.I)
_NON_OUTER_LABEL = re.compile(r"lining|lined|trim|pom|fur|peak|brim|band|badge", re.I)
_NON_OUTER_AFTER = re.compile(r"\s*(lining|lined|trim|pom)\b", re.I)


def _composition_runs(text: str) -> Iterable[Tuple[List[re.Match], str, str]]:
    """把连续的 "xx% 纤维" 合并成一组，返回 (条目, 前文标签, 后文)。"""
    run: List[re.Match] = []
    prev_end = 0
    for m in _ITEM.finditer(text):
        if run and _JOINER.fullmatch(text[run[-1].end():m.start()]):
            run.append(m)
            continue
        if run:
            yield run, text[max(prev_end, run[0].start() - 16):run[0].start()], text[run[-1].end():]
            prev_end = run[-1].end()
        run = [m]
    if run:
        yield run, text[max(prev_end, run[0].start() - 16):run[0].start()], text[run[-1].end():]


def _format(run: List[re.Match]) -> str:
    merged: dict[str, int] = {}
    for m in run:
        zh = FIBER_ZH[m.group(2).lower()]
        merged[zh] = merged.get(zh, 0) + int(m.group(1))
    if merged == {"棉": 100}:
        return "纯棉100%"   # 与已备案样例写法一致
    return "、".join(f"{zh}{pct}%" for zh, pct in merged.items())


def extract_outer_composition(descriptions: Iterable[str]) -> str:
    """按顺序查找各段描述，返回第一个外层成分，如 "腈纶100%"；提取不到返回 ""。"""
    for text in descriptions:
        for run, label, after in _composition_runs(text or ""):
            if sum(int(m.group(1)) for m in run) != 100:
                continue
            if not _OUTER_LABEL.search(label) and (
                _NON_OUTER_LABEL.search(label) or _NON_OUTER_AFTER.match(after)
            ):
                continue
            return _format(run)
    return ""
