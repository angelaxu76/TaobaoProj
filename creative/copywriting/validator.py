# -*- coding: utf-8 -*-
"""文案校验：字数、字符、广告法词、事实依据、季节、颜色。"""
from __future__ import annotations

import re

from cfg.creative_config import (
    COPY_EXTRA_BANNED, COPY_LIMITS, FACT_RULES, LATIN_CHAR_WEIGHT, SEASON_CONFLICTS, WATER_CLAIM_PROOF,
    WATER_CLAIM_RESIST, WATER_IGNORE, WATER_NEGATED, WATER_OVERCLAIM, WATER_PROOF, WATER_RESIST, WATER_STRONG,
)
from common.text.ad_sanitizer import _load_words
from creative.product_source import ProductInfo

_COLOR_RE = re.compile(r"([黑白红蓝绿棕灰粉黄紫橙银金米])(?:色|调|配)")


def text_length(s: str) -> float:
    """汉字及全角字符算 1，英文/数字/空格按 LATIN_CHAR_WEIGHT。"""
    return sum(LATIN_CHAR_WEIGHT if ord(ch) < 0x2E80 else 1 for ch in s or "")


def mentions_color(text: str) -> bool:
    return bool(_COLOR_RE.search(text or ""))


def check_length(text: str, field: str) -> str:
    n = text_length(text)
    return f"超过{COPY_LIMITS[field]}字（当前{n:g}字）" if n > COPY_LIMITS[field] else ""


def water_level(p: ProductInfo) -> str:
    """防水等级：waterproof / resistant / none（规则见 cfg/creative_config.py）。"""
    ev = p.evidence
    for pat in WATER_IGNORE:
        ev = re.sub(pat, " ", ev)
    resist = bool(re.search(WATER_RESIST, ev))
    if re.search(WATER_NEGATED, ev):
        return "resistant" if resist else "none"
    if re.search(WATER_PROOF, ev):
        strong = re.search(WATER_STRONG, ev) or re.search(WATER_PROOF, p.title.lower())
        return "resistant" if resist and not strong else "waterproof"
    return "resistant" if resist else "none"


def _check_water(text: str, p: ProductInfo) -> list[str]:
    rest = re.sub(WATER_CLAIM_RESIST, "", text)
    proof = re.search(WATER_CLAIM_PROOF, rest)
    resist = re.search(WATER_CLAIM_RESIST, text)
    if not proof and not resist:
        return []
    level = water_level(p)
    errs = []
    if proof and level != "waterproof" and not (proof.group(0) == "雪" and "snow" in p.evidence):
        errs.append(f"「{proof.group(0)}」没有依据（商品{'只是防泼水' if level == 'resistant' else '没有防水功能'}）")
    if resist and level == "none":
        errs.append(f"「{resist.group(0)}」在商品资料中没有依据")
    over = re.search(WATER_OVERCLAIM, text)
    if over:
        errs.append(f"「{over.group(0)}」夸大防水效果")
    return errs


def claim_evidence(texts: list[str], p: ProductInfo) -> str:
    """文案中的功能/材质词 → 英文原文片段，供人工核对。"""
    out = []
    joined = " ".join(t or "" for t in texts)
    rules = [*FACT_RULES, (f"{WATER_CLAIM_RESIST}|{WATER_CLAIM_PROOF}", f"{WATER_PROOF}|{WATER_RESIST}")]
    for cn, en in rules:
        m, e = re.search(cn, joined), re.search(en, p.evidence, re.IGNORECASE)
        if m and e:
            out.append(f"{m.group(0)}: …{p.evidence[max(0, e.start() - 30):e.end() + 30].strip()}…")
    return "\n".join(out)


def check_copy(text: str, field: str, product: ProductInfo, category_cn: str) -> list[str]:
    """校验卖点 / 推荐理由，返回问题列表（空 = 通过）。"""
    if not text:
        return ["为空"]
    errs = [e for e in [check_length(text, field)] if e]
    if text_length(text) < 4:
        errs.append("太短")
    if re.search(r"[^一-鿿0-9 ]", text):
        errs.append("只能包含汉字、数字、空格")
    for w in [*_load_words(), *COPY_EXTRA_BANNED]:
        if w and w in text:
            errs.append(f"含禁用词「{w}」")
    ev = product.evidence
    for cn, en in FACT_RULES:
        m = re.search(cn, text)
        if m and not re.search(en, ev, re.IGNORECASE):
            errs.append(f"「{m.group(0)}」在商品资料中没有依据")
    errs += _check_water(text, product)
    for cn, cats in SEASON_CONFLICTS:
        m = re.search(cn, text)
        if m and category_cn in cats:
            errs.append(f"「{m.group(0)}」与{category_cn}季节不符")
    for ch in _COLOR_RE.findall(text):
        if ch not in product.color_cn:
            errs.append(f"颜色「{ch}」与商品颜色「{product.color_cn or '未知'}」不符")
    return errs
