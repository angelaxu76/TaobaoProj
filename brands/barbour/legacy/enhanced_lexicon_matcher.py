# -*- coding: utf-8 -*-
"""
增强版 Lexicon 匹配器

改进点：
1. 多阶段召回（严格 → 宽松 → 兜底）
2. 颜色同义词 + 模糊匹配
3. 标题文本相似度
4. 动态阈值
5. 4维度打分（L1 + L2 + 颜色 + 标题相似度）

使用方式：
    from brands.barbour.core.enhanced_lexicon_matcher import EnhancedLexiconMatcher

    matcher = EnhancedLexiconMatcher(raw_conn)
    product_code, debug = matcher.match(
        scraped_title="Barbour Ashby Wax Jacket",
        scraped_color="Navy",
    )
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher

# ================== 配置 ==================

# 颜色同义词表
COLOR_SYNONYMS = {
    "navy": ["navy", "navy blue", "dark blue", "marine"],
    "olive": ["olive", "archive olive", "sage olive", "khaki"],
    "black": ["black", "jet", "noir", "jet black"],
    "brown": ["brown", "tan", "rustic", "bark"],
    "green": ["green", "sage", "forest"],
    "red": ["red", "russet", "brick"],
    "grey": ["grey", "gray", "charcoal"],
    "blue": ["blue", "royal blue", "sky blue"],
}

# 权重配置（4维度）
WEIGHT_L1 = 0.35        # L1关键词（降低）
WEIGHT_L2 = 0.25        # L2关键词
WEIGHT_COLOR = 0.25     # 颜色匹配（提高）
WEIGHT_TITLE = 0.15     # 标题相似度（新增）

# 阈值配置
BASE_MIN_SCORE = 0.65   # 基础最低分（降低）
BASE_MIN_LEAD = 0.03    # 基础领先优势（降低）


# ================== 工具函数 ==================

def _normalize_ascii(text: str) -> str:
    """标准化为ASCII"""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _tokenize(text: str, min_length: int = 3) -> List[str]:
    """文本分词"""
    t = _normalize_ascii(text).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = [w for w in t.split() if len(w) >= min_length]
    return words


def _dedupe_keep_order(words: List[str]) -> List[str]:
    """去重保持顺序"""
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _normalize_color_name(color: str) -> str:
    """标准化颜色名称"""
    if not color or color == "No Data":
        return ""

    c = color.strip()
    c = re.sub(r"\s+[A-Z]{1,3}\d{2,3}\b", "", c).strip()  # 去掉 OL71/NY91
    c = c.split("/")[0].strip()
    c = c.split("-")[0].strip()
    c = re.sub(r"[^A-Za-z\s]", " ", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c.lower()


def _saturating_score(k: int) -> float:
    """饱和打分"""
    if k <= 0:
        return 0.0
    if k == 1:
        return 0.70   # 降低单个匹配的分数
    if k == 2:
        return 0.85
    if k == 3:
        return 0.95
    return 1.0


# ================== 颜色匹配增强 ==================

def color_similarity(c1: str, c2: str) -> float:
    """
    颜色相似度计算

    Returns:
        0.0 - 1.0 (1.0=完全匹配)
    """
    if not c1 or not c2:
        return 0.0

    c1 = c1.lower().strip()
    c2 = c2.lower().strip()

    # 1. 精确匹配
    if c1 == c2:
        return 1.0

    # 2. 同义词匹配
    for syn_group in COLOR_SYNONYMS.values():
        if c1 in syn_group and c2 in syn_group:
            return 0.95

    # 3. 包含关系
    if c1 in c2 or c2 in c1:
        return 0.85

    # 4. 模糊匹配（编辑距离）
    ratio = SequenceMatcher(None, c1, c2).ratio()
    if ratio >= 0.8:
        return 0.80

    return 0.0


# ================== 标题相似度 ==================

def title_similarity(scraped: str, candidate: str) -> float:
    """
    标题相似度计算

    Returns:
        0.0 - 1.0 (1.0=完全相同)
    """
    if not scraped or not candidate:
        return 0.0

    # 标准化
    s1 = _normalize_ascii(scraped).lower()
    s2 = _normalize_ascii(candidate).lower()

    # 方法1: 序列匹配
    seq_ratio = SequenceMatcher(None, s1, s2).ratio()

    # 方法2: Jaccard相似度（词集合）
    words1 = set(_tokenize(s1, min_length=2))
    words2 = set(_tokenize(s2, min_length=2))

    if not words1 or not words2:
        return 0.0

    jaccard = len(words1 & words2) / len(words1 | words2)

    # 取两者最大值
    return max(seq_ratio, jaccard)


# ================== 增强匹配器 ==================

class EnhancedLexiconMatcher:
    """
    增强版 Lexicon 匹配器
    """

    def __init__(self, raw_conn, table: str = "barbour_products", brand: str = "barbour"):
        self.raw_conn = raw_conn
        self.table = re.sub(r"[^a-zA-Z0-9_]", "", table)
        self.brand = brand

        # 加载 Lexicon
        self.l1_set = self._load_lexicon_set(level=1)
        self.l2_set = self._load_lexicon_set(level=2)

    def _load_lexicon_set(self, level: int) -> set:
        """加载词库"""
        sql = """
            SELECT keyword
            FROM keyword_lexicon
            WHERE brand=%s AND level=%s AND is_active=true
        """

        with self.raw_conn.cursor() as cur:
            cur.execute(sql, (self.brand, level))
            return {str(r[0]).strip().lower() for r in cur.fetchall() if r and r[0]}

    def match(
        self,
        scraped_title: str,
        scraped_color: str,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        匹配商品

        Returns:
            (product_code, debug_info)
        """
        debug = {
            "scraped_title": scraped_title,
            "scraped_color": scraped_color,
            "scraped_l1": [],
            "scraped_l2": [],
            "candidates": 0,
            "top": [],
            "reason": "",
            "recall_stage": 0,
        }

        # 提取关键词
        scraped_l1 = self._extract_keywords(scraped_title, self.l1_set)
        scraped_l2 = self._extract_keywords(scraped_title, self.l2_set)
        scraped_color_norm = _normalize_color_name(scraped_color)

        debug["scraped_l1"] = scraped_l1
        debug["scraped_l2"] = scraped_l2

        # ========== 多阶段召回 ==========

        # 阶段1: 严格召回（L1 ≥ 2）
        if len(scraped_l1) >= 2:
            rows = self._recall_by_l1(scraped_l1, limit=2500)
            debug["recall_stage"] = 1
            debug["candidates"] = len(rows)

            if rows:
                return self._rank_and_select(
                    rows, scraped_title, scraped_l1, scraped_l2, scraped_color_norm, debug
                )

        # 阶段2: 宽松召回（L1 ≥ 1）
        if len(scraped_l1) >= 1:
            rows = self._recall_by_l1(scraped_l1, limit=3000)
            debug["recall_stage"] = 2
            debug["candidates"] = len(rows)

            if rows:
                return self._rank_and_select(
                    rows, scraped_title, scraped_l1, scraped_l2, scraped_color_norm, debug,
                    min_score=BASE_MIN_SCORE - 0.05,  # 降低阈值
                    min_lead=BASE_MIN_LEAD - 0.01,
                )

        # 阶段3: 兜底召回（使用分词 + 颜色）
        if scraped_color_norm:
            rows = self._recall_by_color(scraped_color_norm, limit=500)
            debug["recall_stage"] = 3
            debug["candidates"] = len(rows)

            if rows:
                return self._rank_and_select(
                    rows, scraped_title, scraped_l1, scraped_l2, scraped_color_norm, debug,
                    min_score=BASE_MIN_SCORE - 0.10,  # 进一步降低阈值
                    min_lead=BASE_MIN_LEAD - 0.02,
                )

        # 所有阶段都失败
        debug["reason"] = "FAIL_NO_RECALL"
        return None, debug

    def _extract_keywords(self, text: str, lex_set: set) -> List[str]:
        """提取关键词"""
        tokens = _tokenize(text)
        hits = [w for w in tokens if w in lex_set]
        return _dedupe_keep_order(hits)

    def _recall_by_l1(self, scraped_l1: List[str], limit: int) -> List:
        """通过 L1 关键词召回"""
        sql = f"""
            SELECT DISTINCT ON (product_code, color)
                product_code,
                style_name,
                color,
                match_keywords_l1,
                match_keywords_l2,
                source_rank
            FROM {self.table}
            WHERE match_keywords_l1 && %s::text[]
            ORDER BY product_code, color, source_rank ASC
            LIMIT %s
        """

        with self.raw_conn.cursor() as cur:
            cur.execute(sql, (scraped_l1, limit))
            return cur.fetchall()

    def _recall_by_color(self, color_norm: str, limit: int) -> List:
        """通过颜色召回（兜底）"""
        sql = f"""
            SELECT DISTINCT ON (product_code, color)
                product_code,
                style_name,
                color,
                match_keywords_l1,
                match_keywords_l2,
                source_rank
            FROM {self.table}
            WHERE LOWER(color) LIKE %s
            ORDER BY product_code, color, source_rank ASC
            LIMIT %s
        """

        with self.raw_conn.cursor() as cur:
            cur.execute(sql, (f"%{color_norm}%", limit))
            return cur.fetchall()

    def _rank_and_select(
        self,
        rows: List,
        scraped_title: str,
        scraped_l1: List[str],
        scraped_l2: List[str],
        scraped_color_norm: str,
        debug: Dict,
        min_score: float = BASE_MIN_SCORE,
        min_lead: float = BASE_MIN_LEAD,
    ) -> Tuple[Optional[str], Dict]:
        """排序和选择"""

        # 动态阈值
        num_candidates = len(rows)
        if num_candidates < 10:
            min_score -= 0.05
            min_lead -= 0.01

        scored = []

        for (product_code, style_name, color, kw_l1, kw_l2, source_rank) in rows:
            cand_l1 = list(kw_l1 or [])
            cand_l2 = list(kw_l2 or [])
            cand_color_norm = _normalize_color_name(color or "")

            # 计算各维度得分
            l1_overlap = len(set(cand_l1) & set(scraped_l1))
            l2_overlap = len(set(cand_l2) & set(scraped_l2))

            l1_score = _saturating_score(l1_overlap)
            l2_score = _saturating_score(l2_overlap)
            color_score = color_similarity(scraped_color_norm, cand_color_norm)
            title_score = title_similarity(scraped_title, style_name or "")

            # 4维度加权打分
            score = (
                WEIGHT_L1 * l1_score +
                WEIGHT_L2 * l2_score +
                WEIGHT_COLOR * color_score +
                WEIGHT_TITLE * title_score
            )

            scored.append({
                "product_code": product_code,
                "style_name": style_name,
                "color": color,
                "l1_overlap": l1_overlap,
                "l2_overlap": l2_overlap,
                "l1_score": l1_score,
                "l2_score": l2_score,
                "color_score": color_score,
                "title_score": title_score,
                "score": score,
                "source_rank": source_rank,
            })

        if not scored:
            debug["reason"] = "FAIL_NO_SCORED"
            return None, debug

        # 排序
        scored.sort(key=lambda x: x["score"], reverse=True)

        top = scored[:20]
        debug["top"] = top

        best = top[0]
        second = top[1] if len(top) >= 2 else None

        # 阈值判断
        if best["score"] < min_score:
            debug["reason"] = f"FAIL_LOW_SCORE (score={best['score']:.3f} < {min_score})"
            return None, debug

        if second is not None:
            lead = best["score"] - second["score"]
            if lead < min_lead:
                debug["reason"] = f"FAIL_LOW_LEAD (lead={lead:.3f} < {min_lead})"
                return None, debug

        debug["reason"] = "OK"
        return best["product_code"], debug
