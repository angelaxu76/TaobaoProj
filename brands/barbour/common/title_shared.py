# -*- coding: utf-8 -*-
"""
Barbour 标题生成共享工具。

只放与品类无关的通用算法（字节长度计算 / 颜色映射 / 系列名提取 / 60字节补齐框架）。
品类专属的词表（前缀规则、卖点词、噪声词等）留在各自的标题生成脚本里：
    - generate_taobao_title_v2.py           服装/夹克类
    - generate_taobao_title_accessories.py  配件类（包/帽子/围巾/皮带等）
两边都从本模块 import 通用函数，避免各自维护一份重复算法。
"""
import re
import random
import unicodedata

from config import BARBOUR

# ==== 颜色映射（Barbour 全品类共用一张色卡）====
COLOR_MAP = BARBOUR["BARBOUR_COLOR_MAP"]


def get_byte_length(text: str) -> int:
    return len((text or "").encode("gbk", errors="ignore"))


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).strip()


def map_color(color_en: str) -> str:
    c = nfkc(color_en)
    c = re.sub(r"^[\-\:\|•\.\s]+", "", c)  # 去掉开头 "- "
    c = c.split("/")[0].strip()  # 复合色取第一色
    cl = c.lower()
    if cl in COLOR_MAP:
        return COLOR_MAP[cl]
    cl2 = re.sub(r"^(classic|washed|burnt|dark|light)\s+", "", cl).strip()
    return COLOR_MAP.get(cl2, c)


def detect_material_cn(style_name_en: str, material_hints: list) -> str:
    """material_hints: [(regex_pattern, 中文材质), ...]，由调用方按品类提供。"""
    s = (style_name_en or "").lower()
    for pat, zh in material_hints:
        if re.search(pat, s, flags=re.I):
            return zh
    return ""


def detect_keyword_tags(style_name_en: str, keyword_map: dict) -> list:
    """按 keyword_map（英文关键词→中文标签）匹配，返回命中的中文标签列表（去重，保序）。"""
    text = (style_name_en or "").lower()
    tags = []
    for kw, zh in keyword_map.items():
        if kw in text and zh not in tags:
            tags.append(zh)
    return tags


def _normalize_token(t: str) -> str:
    """把 "Men's" / "Men’s" -> "mens"，并去掉末尾 's。"""
    if not t:
        return ""
    t = t.strip().lower().replace("’", "'")
    if t.endswith("'s"):
        t = t[:-2]
    return t


def detect_series(style_name_en: str, whitelist: set, blacklist: set, noise: set) -> str:
    """
    从英文款式名里提取系列/款式词。
    1) 命中白名单（且不在黑名单）优先返回；
    2) 否则兜底挑第一个不在黑名单/噪声词里的"有意义"词（长度>2）。
    白名单/黑名单/噪声词由调用方按品类各自提供。
    """
    s = nfkc(style_name_en)
    tokens_raw = re.findall(r"[A-Za-z][A-Za-z'-]+", s)
    tokens = [_normalize_token(t) for t in tokens_raw]

    for t_raw, t in zip(tokens_raw, tokens):
        if t in blacklist:
            continue
        if t in whitelist:
            disp = t_raw.replace("’", "'")
            if disp.lower().endswith("'s"):
                disp = disp[:-2]
            return disp.capitalize()

    for t_raw, t in zip(tokens_raw, tokens):
        if t in blacklist or t in noise:
            continue
        if len(t) <= 2:
            continue
        disp = t_raw.replace("’", "'")
        if disp.lower().endswith("'s"):
            disp = disp[:-2]
        return disp.capitalize()

    return ""


def pad_to_60_bytes(
    base_title: str,
    style_name_en: str,
    type_str: str,
    keyword_map: dict,
    type_core_keywords: dict,
    type_extras: dict,
    filler_words: list,
) -> str:
    """
    补齐到 60 字节，优先级：
    1) keyword_map 命中的关键词标签（国际版/防水/轻蜡…）
    2) type_core_keywords 核心品类词（近义词，如 外套/内胆）
    3) type_extras 类型卖点词（通勤/百搭/春秋…）
    4) filler_words 通用安全词
    各词表由调用方（夹克/配件）各自提供。
    """
    cur = base_title or ""
    if get_byte_length(cur) >= 60:
        return cur

    available = 60 - get_byte_length(cur)

    for tag in detect_keyword_tags(style_name_en, keyword_map):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    for tag in type_core_keywords.get(type_str, []):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    for tag in type_extras.get(type_str, []):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    if available > 0:
        words = filler_words[:]
        random.shuffle(words)
        for w in words:
            if available <= 0:
                break
            if w in cur:
                continue
            wlen = get_byte_length(w)
            if wlen <= available:
                cur += w
                available -= wlen

    return cur
