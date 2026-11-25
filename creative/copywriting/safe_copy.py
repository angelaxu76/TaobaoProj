# -*- coding: utf-8 -*-
"""
保守模式（默认）：卖点 / 推荐理由只用可核实的事实 + 中性短语拼出来，不调用 AI。

  卖点1 = 材质 + 颜色           例：磨砂皮面 经典黑色
  卖点2 = 原文明确写到的功能/穿法  例：防水设计 系带款式
  推荐理由 = 中性短语             例：日常出行 百搭之选

事实来源与规则：
  颜色：库存表 color（已翻成中文）。英文、多色、空 → 不写具体颜色
  材质：成分比例（材质字段 / 描述里的 Upper:、Outer:、100% xx）> 英文标题 > 成分文字，按 SAFE_MATERIALS 词表；
        描述正文不用（常是领口、饰边的材质）；主成分 < 95% 写「xx混纺」
  功能：SAFE_FEATURES，每条都要原文有明确英文说法；防水按 water_level 分级
不写任何体验承诺（久穿不累、不磨脚、显瘦、柔软舒适…）。词表在 cfg/creative_config.py，可增删。
"""
from __future__ import annotations

import hashlib
import re

from cfg.creative_config import (
    SAFE_BLEND_OK, SAFE_BLEND_THRESHOLD, SAFE_FEATURES, SAFE_FILLERS, SAFE_MATERIALS, SAFE_REASONS,
    SAFE_WATER_RESIST,
)
from common.text.style_extractors import strip_trademarks
from creative.copywriting.validator import check_copy, water_level
from creative.product_source import ProductInfo

_SHOE_TAIL = ("鞋", "靴", "拖", "莫卡辛")


def _pick(p: ProductInfo, salt: str, options: list[str]) -> str:
    h = int(hashlib.md5(f"{p.product_code}|{salt}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def _first_material(text: str) -> tuple[int, str] | None:
    best = None
    for pat, cn in SAFE_MATERIALS:
        m = re.search(rf"(?<![a-z])(?:{pat})(?![a-z])", text or "", re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), cn)
    return best


def _composition(p: ProductInfo) -> str:
    """成分段：Upper:/Outer:/Shell: 后面的文字；材质字段本身也算成分。"""
    for text in (p.material, p.description, p.feature):
        m = re.search(r"(?:upper|outer|shell|main fabric|body)\s*(?:fabric|material)?\s*:\s*(.{0,80}?)"
                      r"(?:lining|outsole|sole|insole|trim|sleeve|$)", text, re.I)
        if m:
            return m.group(1)
    return p.material


def material_cn(p: ProductInfo) -> str:
    """主材质中文名；找不到返回空。"""
    comp = _composition(p)
    pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*([a-z][a-z \-]*)", comp, re.I)
    title_hit = _first_material(strip_trademarks(p.title))
    if title_hit and not pct:
        return title_hit[1]
    if pct:      # 有成分比例时以成分为准（标题 Cotton Wool Jacket 实际是 80% 棉混纺）
        hit = _first_material(pct.group(2))
        if not hit:
            return ""
        if float(pct.group(1).replace(",", ".")) >= SAFE_BLEND_THRESHOLD:
            return hit[1]
        return f"{hit[1].removesuffix('质')}混纺" if hit[1] in SAFE_BLEND_OK else ""
    hit = _first_material(comp)
    return hit[1] if hit else ""


def color_phrase(p: ProductInfo) -> str:
    c = p.color_cn.strip()
    if not re.fullmatch(r"[一-鿿]{1,4}", c) or c == "多色":
        return ""   # 英文、多色（可能是格纹/拼色/印花，无法确定）都不写
    c = c if c.endswith("色") else c + "色"
    return f"经典{c}" if len(c) <= 2 else c[:4]


def feature_phrases(p: ProductInfo, category_cn: str) -> list[str]:
    ev = p.evidence
    level = water_level(p)
    out = ["防水设计"] if level == "waterproof" else []
    if level == "resistant" and re.search(SAFE_WATER_RESIST, ev, re.I):
        out.append("防泼水面")
    for phrase, pattern, shoe_only in SAFE_FEATURES:
        if shoe_only and not category_cn.endswith(_SHOE_TAIL):
            continue
        redundant = {"系带款式": "弹力鞋带", "连帽设计": "可拆连帽", "保暖设计": "保暖内里"}
        if redundant.get(phrase) in out or (phrase == "拉链设计" and category_cn.endswith("包")):  # 包的拉链多是内袋
            continue
        if re.search(pattern, ev, re.I) and phrase not in out:
            out.append(phrase)
    return out


def generate_safe(p: ProductInfo, category_cn: str) -> dict:
    mat = material_cn(p)
    color = color_phrase(p)
    feats = feature_phrases(p, category_cn)
    parts1 = [x for x in ((f"{mat}材质" if len(mat) <= 3 else mat) if mat else "", color) if x]
    parts2, spare = feats[:2], feats[2:]
    while len(parts1) < 2 and spare:          # 材质/颜色缺的，用多出来的功能补
        parts1.append(spare.pop(0))

    def fill(parts: list[str], salt: str) -> str:
        while len(parts) < 2:                  # 剩余空位用中性短语，同一句内不重复
            parts.append(_pick(p, f"{salt}{len(parts)}", [f for f in SAFE_FILLERS if f not in parts]))
        return " ".join(parts)

    sp1, sp2 = fill(parts1, "f1"), fill(parts2, "f2")

    reason = _pick(p, "r", [r for r in SAFE_REASONS if r not in (sp1, sp2)])

    vals = {"selling_point_1": sp1, "selling_point_2": sp2, "recommend_reason": reason}
    for f, v in vals.items():    # 兜底再过一遍事实校验，理论上不会触发
        if check_copy(v, f, p, category_cn):
            vals[f] = "日常百搭 出行实用"
    return {**vals, "copy_source": "safe"}
