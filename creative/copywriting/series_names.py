# -*- coding: utf-8 -*-
"""系列英文名 → 中文名。优先级：cfg 配置 > series_names.json > AI 翻译（写入 series_names.json，各次运行保持一致）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from cfg.brand_strategy import BRAND_NAME_MAP
from cfg.creative_config import COPY_LIMITS, SERIES_CN_MAP
from common.text.style_extractors import ecco_series_cn
from creative.copywriting import llm
from creative.copywriting.naming import brand_name

NAMES_FILE = Path(__file__).with_name("series_names.json")   # {品牌: {大写英文系列名: 中文名}}，可直接编辑
_BATCH = 40


def _max_len(brand: str) -> int:
    """宝贝名称 8 字 = 品牌 + 系列 + 商品名称 3 字；系列中文名 2~3 字。"""
    return min(3, max(2, COPY_LIMITS["item_name"] - 3 - len(brand_name(brand))))


def _load_names() -> dict[str, dict[str, str]]:
    return json.loads(NAMES_FILE.read_text(encoding="utf-8")) if NAMES_FILE.exists() else {}


def _save_names(brand: str, new: dict[str, str]) -> None:
    names = _load_names()
    names[brand] = dict(sorted({**new, **names.get(brand, {})}.items()))   # 已有的（可能人工改过）优先
    NAMES_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")


def configured_series_cn(brand: str, core: str) -> str:
    cn = SERIES_CN_MAP.get(brand, {}).get(core, "")
    if not cn and brand == "ecco":
        cn = ecco_series_cn(core)
    return cn


def _translate(brand: str, cores: list[str]) -> dict[str, str]:
    """字数不合格的会再试一轮。"""
    out = _translate_once(brand, cores)
    failed = [c for c in cores if c not in out]
    if failed:
        out.update(_translate_once(brand, failed))
    return out


def _translate_once(brand: str, cores: list[str]) -> dict[str, str]:
    en = BRAND_NAME_MAP.get(brand, (brand, ""))[0]
    n = _max_len(brand)
    out: dict[str, str] = {}
    for i in range(0, len(cores), _BATCH):
        batch = cores[i:i + _BATCH]
        data = llm.chat_json([
            {"role": "system", "content":
                f"你为品牌 {en} 的商品系列名起中文名，用于淘宝标题。要求：{'必须正好 2 个汉字，音译太长就只取前两个音' if n == 2 else f'2~{n} 个汉字，音译太长就截短'}；"
                "人名地名用通行音译，有含义的普通英文词用意译，自造词用好听的音译；"
                "只用汉字，不要出现鞋、靴、衣等品类字，不要夸大或贬义；不要用其他品牌的名字；不同系列不要重名。"
                "输出 JSON 对象：键为原英文（原样照抄），值为中文名。"},
            {"role": "user", "content": "系列名：\n" + "\n".join(batch)},
        ], temperature=0.3) or {}
        for c in batch:
            v = str(data.get(c, "")).strip()
            if re.fullmatch(rf"[一-鿿]{{2,{n}}}", v):
                out[c] = v
    return out


def resolve_series_cn(brand: str, cores: set[str], use_ai: bool = True) -> dict[str, str]:
    """core → 中文名（没有则不在结果里）。"""
    cached = _load_names().get(brand, {})
    result = {c: configured_series_cn(brand, c) or cached.get(c, "") for c in cores if c}
    missing = sorted(c for c in result if not result[c] and re.search(r"[A-Z]{2}", c))
    if use_ai and missing and llm.available():
        print(f"🔤 [{brand}] AI 翻译 {len(missing)} 个系列名 → {NAMES_FILE.name}")
        new = _translate(brand, missing)
        if new:
            _save_names(brand, new)
        result.update(new)
    return {k: v for k, v in result.items() if v}
