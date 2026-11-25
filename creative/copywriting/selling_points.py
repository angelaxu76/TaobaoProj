# -*- coding: utf-8 -*-
"""卖点1 / 卖点2 / 推荐理由：DeepSeek 按商品资料生成 → 规则校验 + AI 事实核查，不过则重写，仍不过用规则短语兜底。"""
from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path

from cfg.creative_config import COPY_LABELS, COPY_LIMITS, REASON_ANGLES
from creative.copywriting import llm
from creative.copywriting.naming import gender_word
from creative.copywriting.validator import check_copy, water_level
from creative.product_source import ProductInfo

FIELDS = ["selling_point_1", "selling_point_2", "recommend_reason"]
EXAMPLES_FILE = Path(__file__).with_name("style_examples.txt")


@lru_cache(maxsize=1)
def _examples() -> list[str]:
    lines = EXAMPLES_FILE.read_text(encoding="utf-8-sig").splitlines()
    return list(dict.fromkeys(x.strip() for x in lines if x.strip()))


_SYSTEM = f"""你是淘宝资深文案，根据英文商品资料写中文短文案。输出 JSON：
{{"selling_point_1": "", "selling_point_2": "", "recommend_reason": ""}}
- selling_point_1 / selling_point_2（卖点）：各不超过{COPY_LIMITS['selling_point_1']}个字（空格也算），用"四字 四字"两段，中间一个空格。两条角度必须不同，例如一条写材质/工艺/科技，一条写穿着体验或版型。
- recommend_reason（推荐理由）：不超过{COPY_LIMITS['recommend_reason']}个字，可以是"四字 四字"，也可以是一句口语短句，按给出的侧重角度写，体现这个商品的特点；不要与卖点重复，少用"通勤""日常""好搭""皆宜"这类通用词。
规则：
1. 功能和材质只能来自资料，资料没写的（防水、透气、真皮、保暖、减震、防滑、轻便、柔软等）不许写。优先写这个商品最有特点的信息，不要全是套话。
2. 颜色只能用给出的中文颜色；颜色为空或"多色"时不写具体颜色。
3. 不用绝对化和广告法违禁词（最、第一、顶级、完美、极致、首选、保证等），不写价格促销，不写品牌名、系列名，只用汉字，不用标点和英文。
4. 靴子不写夏季，凉鞋不写冬季保暖。
5. 中文自然通顺，不要生造词，不要为凑四字写病句；要让没看过资料的顾客一眼看懂好处，不写生僻的结构名词、数字细节和直译词。"""


_VERIFY = """你是商品文案事实核查员。对照英文商品资料，逐条检查中文短文案里的【具体事实】：材质、工艺、结构部件、功能、产地。
只有资料没写、或与资料矛盾的具体事实才判不通过，例如：鞋垫缓震写成鞋底缓震、内里针织写成鞋面针织、防泼水写成防水、凭空多出"全粒面""六片""哑光"。
合理的同义翻译和概括算通过；主观感受、审美、穿搭和场景建议（有型、百搭、显气质、走路舒服、适合逛街）一律算通过。
输出 JSON：{"selling_point_1": "", "selling_point_2": "", "recommend_reason": ""}，通过写空字符串，不通过写一句原因。"""

_WATER_HINT = {
    "waterproof": "防水（可以写防水、雨天可穿，但不许写无惧、不湿脚、大雨这类夸大的话）",
    "resistant": "仅防泼水（只能写防泼水，不许写防水、雨天、挡雨）",
    "none": "没有防水功能（不许写任何防水、防泼水、雨雪天、防潮的话）",
}


def _rng(p: ProductInfo) -> random.Random:
    return random.Random(f"{p.brand}|{p.product_code}")   # 同一商品结果稳定


def _user_prompt(p: ProductInfo, category_cn: str) -> str:
    ex = _examples()
    rng = _rng(p)
    picked = rng.sample(ex, min(12, len(ex)))
    angle = rng.choice(REASON_ANGLES)
    return (
        f"商品名称：{category_cn}\n适用：{gender_word(p) or '通用'}\n中文颜色：{p.color_cn or '（空）'}\n"
        f"英文标题：{p.title}\n描述：{p.description[:1200]}\n材质：{p.material[:400]}\n特征：{p.feature[:1200]}\n防水等级：{_WATER_HINT[water_level(p)]}\n推荐理由侧重：{angle}\n\n"
        f"风格参考（只学语气和句式，内容以资料为准，不要照抄）：\n" + "\n".join(picked)
    )


def _normalize(v) -> str:
    return re.sub(r"[，,。.、；;！!|/·\s]+", " ", str(v or "")).strip()


def _check_all(vals: dict, p: ProductInfo, category_cn: str) -> dict[str, list[str]]:
    errs, seen = {}, set()
    for f in FIELDS:
        e = check_copy(vals.get(f, ""), f, p, category_cn)
        if vals.get(f) in seen:
            e.append("与其他文案重复")
        seen.add(vals.get(f))
        if e:
            errs[f] = e
    return errs


def _verify(vals: dict, p: ProductInfo) -> dict[str, list[str]]:
    """AI 事实核查。调用失败时视为全部不通过（宁可用规则短语，也不放过未核查的文案）。"""
    data = llm.chat_json([
        {"role": "system", "content": _VERIFY},
        {"role": "user", "content": f"英文标题：{p.title}\n中文颜色：{p.color_cn}\n描述：{p.description}\n材质：{p.material}\n"
                                    f"特征：{p.feature}\n\n待核查文案：{json.dumps(vals, ensure_ascii=False)}"},
    ], temperature=0)
    if data is None:
        return {f: ["事实核查失败"] for f in FIELDS}
    return {f: [f"事实不符：{data[f]}"] for f in FIELDS if str(data.get(f) or "").strip()}


# ── 规则兜底 ───────────────────────────────────────────────────────────────────
# 能否使用由 validator 的事实校验决定，这里只列候选。越靠前越具体。
_RULE_SPECIFIC = [
    "防水设计 雨天可穿", "蜡棉面料 经典质感", "防泼水面料 实用耐看", "羊毛材质 亲肤保暖", "加绒内里 保暖舒适", "磨砂皮面 质感细腻",
    "漆皮光泽 精致亮眼", "缓震鞋底 行走舒适", "记忆鞋垫 贴合足底", "防滑鞋底 稳步出行", "透气材质 舒适不闷",
    "宽楦设计 舒适自在", "轻便设计 久穿不累", "柔软皮革 质感细腻", "弹力设计 贴合舒适", "厚底设计 时尚百搭",
    "拉链设计 穿脱方便", "轻松穿脱 省时省心", "环保材质 舒适安心", "耐磨鞋底 经久耐穿", "亚麻材质 自然舒适",
    "棉质面料 亲肤舒适", "系带设计 贴合脚型",
]
_RULE_GENERIC = ["经典设计 演绎潮流", "简约版型 百搭耐看", "时尚配色 彰显品味", "潮流款式 日常优选", "休闲风格 舒适百搭"]
_RULE_REASON = ["经典百搭 日常优选", "闭眼入不踩雷", "简约时尚 日常百搭", "日常通勤都好搭", "舒适耐看 百搭省心"]


def rule_candidates(field: str, p: ProductInfo, category_cn: str) -> list[str]:
    rng = _rng(p)
    if field == "recommend_reason":
        pool = rng.sample(_RULE_REASON, len(_RULE_REASON))
    else:
        is_shoe = category_cn.endswith(("鞋", "靴", "拖", "莫卡辛"))
        specific = [t for t in _RULE_SPECIFIC if is_shoe or not re.search("鞋|脚|足|步|厚底", t)]
        color_ok = re.fullmatch(r"[一-鿿]{1,3}色", p.color_cn) and p.color_cn != "多色"
        pool = (specific + ([f"经典{p.color_cn} 百搭耐看"] if color_ok else [])
                + rng.sample(_RULE_GENERIC, len(_RULE_GENERIC)))
    return [t for t in pool if not check_copy(t, field, p, category_cn)]


def generate_selling_points(p: ProductInfo, category_cn: str, use_ai: bool = True) -> dict:
    """返回 {selling_point_1, selling_point_2, recommend_reason, copy_source}。"""
    vals: dict[str, str] = {}
    errs: dict[str, list[str]] = {f: ["未生成"] for f in FIELDS}
    if use_ai and llm.available():
        base = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _user_prompt(p, category_cn)}]
        messages = base
        for _ in range(3):
            data = llm.chat_json(messages)
            if data is None:
                break
            for f in errs:                           # 只替换没通过的字段
                vals[f] = _normalize(data.get(f))
            errs = _check_all(vals, p, category_cn) or _verify(vals, p)
            if not errs:
                break
            problems = "；".join(f"{COPY_LABELS[f]}「{vals.get(f, '')}」：{'、'.join(e)}" for f, e in errs.items())
            messages = base + [
                {"role": "assistant", "content": json.dumps(vals, ensure_ascii=False)},
                {"role": "user", "content": f"以下不合格，请改写后重新输出完整 JSON：{problems}"},
            ]

    bad = list(errs)
    used = {vals[f] for f in FIELDS if f not in errs}
    for f in bad:
        vals[f] = next((t for t in rule_candidates(f, p, category_cn) if t not in used), "")
        used.add(vals[f])
    source = "ai" if not bad else "rule" if len(bad) == len(FIELDS) else "mixed"
    return {**{f: vals[f] for f in FIELDS}, "copy_source": source}
