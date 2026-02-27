# -*- coding: utf-8 -*-
"""
keyword_lexicon 词库导入工具

用法：
  from brands.barbour.core.import_keywords_lexicon import import_lexicon_from_titles
  import_lexicon_from_titles(titles_path="...", l1_file="...", brand="barbour")

或直接运行（需传参）：
  python -m brands.barbour.core.import_keywords_lexicon \
      --titles path/to/titles.txt \
      --l1-file path/to/keywords_style_only.txt \
      [--brand barbour]
"""

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

import psycopg2
from psycopg2.extras import execute_values

from config import PGSQL_CONFIG


# ====================== 停用词表 ======================

STOPWORDS_COMMON = {
    "the", "and", "or", "with", "for", "of", "in", "on",
    "by", "to", "from", "this", "that", "these", "those",
    "new", "not", "all"
}

STOPWORDS_GENDER = {
    "men", "mens", "man", "male",
    "women", "womens", "woman", "female",
    "boy", "boys", "girl", "girls",
    "kids", "kid", "child", "children",
    "unisex", "ladies", "lady"
}

STOPWORDS_CATEGORY = {
    "jacket", "jackets", "coat", "coats", "parka", "anorak",
    "blazer", "bomber", "overcoat", "overshirt", "duffle",
    "smock", "trench", "waistcoat", "gilet", "gilets", "vest",
    "trouser", "trousers", "pants", "jeans", "leggings",
    "shorts", "skirt", "tracksuit",
    "boot", "boots", "shoe", "shoes", "slipper", "slippers",
    "sandals", "trainer", "trainers",
    "bag", "bags", "backpack", "belt", "wallet", "purse", "tote",
    "umbrella", "hat", "hats", "cap", "caps", "beanie", "beret",
    "scarf", "scarves", "glove", "gloves", "socks", "stockings",
    "shirt", "shirts", "tee", "tshirt", "top", "tops",
    "jumper", "sweater", "sweatshirt", "sweatshirts", "hoodie",
    "cardigan", "knit", "knitted",
    "dress", "dresses",
}

STOPWORDS_FEATURE = {
    "quilted", "quilt", "wax", "waxed", "padded", "lined",
    "liner", "insulated", "lightweight", "waterproof",
    "showerproof", "windproof", "detachable", "reversible",
    "removable", "hood", "hooded", "collared", "collarless",
    "zip", "zipper", "button", "buttons", "pocket", "pockets",
    "collar", "stand", "fit", "fitted", "sleeve", "sleeves",
    "sleeved", "sleeveless", "zippered", "zipped",
    "length", "lining", "inner", "outer",
}

STOPWORDS_MARKETING = {
    "classic", "modern", "vintage", "heritage",
    "original", "originals", "signature", "essential",
    "essentials", "premium", "casual", "smart",
    "relaxed", "tailored", "regular", "slim",
    "oversized", "longline", "cropped",
}

STOPWORDS_COLOR = {
    "black", "navy", "olive", "green", "brown", "white",
    "grey", "gray", "khaki", "beige", "cream", "stone",
    "sage", "rust", "pink", "blue", "silver", "gold",
    "charcoal", "camel", "red",
}

STOPWORDS_BRAND = {"barbour", "international"}

# L2：描述 / 材质 / 季节 / 风格词（带 category 入库）
STOPWORDS_L2: Dict[str, str] = {
    # style
    "style": "style",
    "classic": "style", "modern": "style", "vintage": "style", "heritage": "style",
    "original": "style", "signature": "style", "essential": "style", "premium": "style",
    "preppy": "style", "casual": "style", "smart": "style", "relaxed": "style",
    "rugged": "style", "sport": "style", "sports": "style", "utility": "style", "uniform": "style",
    # material
    "suede": "material", "leather": "material", "cotton": "material", "wool": "material",
    "canvas": "material", "denim": "material", "linen": "material", "nubuck": "material",
    "cashmere": "material", "merino": "material", "nylon": "material", "corduroy": "material",
    "tweed": "material", "velvet": "material", "satin": "material", "silk": "material",
    "fleece": "material", "fur": "material", "microfleece": "material", "softshell": "material",
    "lambswool": "material", "moleskin": "material",
    # season / occasion
    "summer": "season", "winter": "season", "spring": "season", "autumn": "season", "fall": "season",
    "seasonal": "season",
    "warm": "season", "cool": "season", "weather": "season",
    "outdoor": "occasion", "travel": "occasion", "weekender": "occasion",
    # function
    "waterproof": "function", "showerproof": "function", "windproof": "function",
    "resistant": "function", "breathable": "function", "durable": "function",
    "technical": "function", "performance": "function",
    # fit
    "fit": "fit", "fitted": "fit", "tailored": "fit", "regular": "fit", "slim": "fit",
    "oversized": "fit", "long": "fit", "short": "fit", "cropped": "fit", "length": "fit",
    # pattern
    "pattern": "pattern", "patterned": "pattern", "print": "pattern", "printed": "pattern",
    "stripe": "pattern", "striped": "pattern", "plaid": "pattern",
    "check": "pattern", "checked": "pattern", "herringbone": "pattern",
    "houndstooth": "pattern", "texture": "pattern", "textured": "pattern",
}

# L1/L2 之外要过滤的"垃圾词"（不入库）
STOPWORDS_MISC = (
    STOPWORDS_COMMON
    | STOPWORDS_GENDER
    | STOPWORDS_CATEGORY
    | STOPWORDS_FEATURE
    | STOPWORDS_MARKETING
    | STOPWORDS_COLOR
    | STOPWORDS_BRAND
)

L2_GROUPS = {
    "category": STOPWORDS_CATEGORY,
    "feature": STOPWORDS_FEATURE,
    "marketing": STOPWORDS_MARKETING,
    "gender": STOPWORDS_GENDER,
}

MIN_WORD_LENGTH = 3


# ====================== 工具函数 ======================

def normalize_word(word: str) -> str:
    w = (word or "").lower()
    w = re.sub(r"[^a-z]", "", w)
    return w


def tokenize_line(line: str) -> Iterable[str]:
    parts = re.split(r"[\s\-_/]+", line)
    for p in parts:
        w = normalize_word(p)
        if w:
            yield w


def load_l1_set(l1_file: str) -> Set[str]:
    """从文件加载 L1 白名单词表（每行一个词）"""
    return {
        normalize_word(x)
        for x in Path(l1_file).read_text(encoding="utf-8").splitlines()
        if normalize_word(x)
    }


def classify_words_from_titles(
    titles_file: str, l1_set: Set[str]
) -> Tuple[Set[str], Dict[str, str]]:
    """
    从 titles.txt 扫描词并分类：
      - 命中 l1_set       => L1
      - 命中 STOPWORDS_L2 => L2（带 category）
      - 其它              => 丢弃
    """
    l1_words: Set[str] = set()
    l2_words: Dict[str, str] = {}

    lines = Path(titles_file).read_text(encoding="utf-8").splitlines()
    for line in lines:
        for w in tokenize_line(line):
            if len(w) < MIN_WORD_LENGTH:
                continue
            if w in l1_set:
                l1_words.add(w)
                continue
            cat = STOPWORDS_L2.get(w)
            if cat:
                l2_words[w] = cat
                continue

    return l1_words, l2_words


def upsert_keyword_lexicon(
    brand: str, l1_words: Set[str], l2_words: Dict[str, str]
) -> None:
    """将 L1/L2 词库 UPSERT 到 keyword_lexicon 表"""
    merged: Dict[Tuple[int, str], Tuple] = {}

    for w in l1_words:
        merged[(1, w)] = (brand, 1, w, None, 1.0, True)

    for w, cat in l2_words.items():
        merged[(2, w)] = (brand, 2, w, cat, 1.0, True)

    # L2 兜底：从 stopwords 分组补全（已有更细分类的不覆盖）
    for cat, words in L2_GROUPS.items():
        for w in words:
            key = (2, w)
            if key not in merged:
                merged[key] = (brand, 2, w, cat, 1.0, True)

    rows = list(merged.values())
    if not rows:
        print("⚠️ 没有可写入的词")
        return

    sql = """
    INSERT INTO keyword_lexicon (brand, level, keyword, category, weight, is_active)
    VALUES %s
    ON CONFLICT (brand, level, keyword)
    DO UPDATE SET
      category   = COALESCE(EXCLUDED.category, keyword_lexicon.category),
      weight     = EXCLUDED.weight,
      is_active  = EXCLUDED.is_active
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=1000)
        conn.commit()
        l1_cnt = sum(1 for k in merged if k[0] == 1)
        l2_cnt = sum(1 for k in merged if k[0] == 2)
        print(f"✅ keyword_lexicon 写入完成：L1={l1_cnt}，L2={l2_cnt}，总计={len(rows)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ====================== 主入口函数 ======================

def import_lexicon_from_titles(
    titles_path: str,
    *,
    brand: str = "barbour",
    l1_file: Optional[str] = None,
) -> dict:
    """
    一键导入 keyword_lexicon：
      - L1：使用你确认过的 L1 词表文件（keywords_style_only.txt）
      - L2：使用内置 STOPWORDS_L2（带 category）
      - 从 titles.txt 扫描命中的 L1/L2 后 upsert 进数据库

    参数：
      titles_path: titles.txt 路径（每行一个 title）
      brand: 写入 keyword_lexicon.brand 的值
      l1_file: L1 词表文件路径（每行一个词），必须传入

    返回：
      dict: {"brand": ..., "l1_count": ..., "l2_count": ...}
    """
    if not Path(titles_path).exists():
        raise FileNotFoundError(f"titles_path 不存在: {titles_path}")

    if not l1_file:
        raise ValueError(
            "请传入 l1_file（你的 keywords_style_only.txt）。"
            "L1 必须来自确认过的词表，否则会把地名/人名污染进词库。"
        )

    if not Path(l1_file).exists():
        raise FileNotFoundError(f"l1_file 不存在: {l1_file}")

    l1_set = load_l1_set(l1_file)
    l1_words, l2_words = classify_words_from_titles(titles_path, l1_set)
    upsert_keyword_lexicon(brand, l1_words, l2_words)

    return {"brand": brand, "l1_count": len(l1_words), "l2_count": len(l2_words)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="导入 keyword_lexicon 词库")
    ap.add_argument("--titles", required=True, help="titles.txt 路径（每行一个商品标题）")
    ap.add_argument("--l1-file", required=True, help="L1 词表文件路径（每行一个词）")
    ap.add_argument("--brand", default="barbour", help="品牌名（默认 barbour）")
    args = ap.parse_args()

    result = import_lexicon_from_titles(
        titles_path=args.titles,
        l1_file=args.l1_file,
        brand=args.brand,
    )
    print(result)
