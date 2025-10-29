# barbour/match_resolver.py
# -*- coding: utf-8 -*-
"""
通用 color_code 解析器：
- 输入：产品名称 + 颜色 文本（来自任意站点）
- 过程：SQL 端颜色宽松召回 → RapidFuzz 名称打分 + 颜色打分 + 类型加权 → 自适应阈值挑唯一
- 输出：Matched / Unmatched 结果（含候选与分数），供写 TXT / 入库使用
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable

# ======== rapidfuzz（可选） ========
try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False

# 可选：使用你自有的颜色标准化
try:
    from brands.barbour.core.color_utils import normalize_color as _normalize_color
except Exception:
    _normalize_color = None


# ======== 配置：停用词、类别、颜色形容词 ========

COMMON = {
    "barbour","wax","waxed","quilted","shirt","top","tshirt",
    "mens","men","women","womens","ladies","boys","girls","kids","childrens","unisex","size",
    "international",  # ← 新增：避免“Barbour International”影响打分
}
TYPE_TOKENS = {"jacket","gilet","vest","coat","parka","puffer"}  # ← 新增 puffer
COLOR_STOP = {
    "classic","dark","light","true","deep","bright","rich","vintage","muted","modern","antique",
    "original","pure","royal","new","old","heritage"
}
COLOR_FAMILY_KEYS = ["black","navy","olive","bark","brown","green","stone","tan","blue","grey","gray"]


# ======== 数据结构 ========

@dataclass
class Candidate:
    color_code: str
    style_name: str
    color: str

@dataclass
class MatchResult:
    status: str                           # "matched" | "unmatched"
    color_code: Optional[str] = None
    style_name: Optional[str] = None
    score: Optional[float] = None
    # top-K 候选（用于日志或落 unmatched 表）
    candidates: Optional[List[Tuple[str, str, str, float, float, float, float]]] = None
    # (cc, style_name, db_color, name_score, color_score, type_score, total_score)


# ======== 基础清洗与分词 ========

def _normalize_title(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", s or "", flags=re.U)
    return re.sub(r"\s+", " ", s).strip().lower()

def _build_tokens(title: str):
    t = _normalize_title(title)
    return [w for w in t.split() if len(w) >= 3 and w not in COMMON]

def _type_tokens(s: str) -> set:
    t = set(_normalize_title(s).split())
    return {x for x in TYPE_TOKENS if x in t}

def _clean_color_text(color: str) -> str:
    txt = (color or "").strip()
    txt = re.sub(r"\([^)]*\)", "", txt)     # 去括号注释
    txt = re.sub(r"[^\w\s/+-]", " ", txt)   # 去奇怪符号
    txt = re.sub(r"\s+", " ", txt).strip()
    parts = [p for p in txt.split() if not any(c.isdigit() for c in p)]
    return " ".join(parts) if parts else txt

def _color_tokens(color: str) -> set:
    base = _clean_color_text(color).lower()
    toks = [t for t in re.split(r"[\s/+-]+", base) if t and t not in COLOR_STOP]
    return set(toks)

def normalize_color_for_match(color: str) -> str:
    base = _clean_color_text(color)
    if _normalize_color:
        try:
            return _normalize_color(base)
        except Exception:
            pass
    # 简单收敛
    s = base.lower()
    s = re.sub(r"\bnavy\s+blue\b", "navy", s)
    s = re.sub(r"\bjet\s+black\b", "black", s)
    s = re.sub(r"\bdark\s+olive\b", "olive", s)
    return s.title()


# ======== 打分（名称 + 颜色 + 类型） ========

def _name_score(q: str, cand: str) -> float:
    if _HAS_RAPIDFUZZ:
        # 多指标加权，范围 0~1
        return (
            0.5 * (fuzz.token_set_ratio(q, cand) / 100.0)
          + 0.3 * (fuzz.WRatio(q, cand) / 100.0)
          + 0.2 * (fuzz.partial_ratio(q, cand) / 100.0)
        )
    # 兜底：token Jaccard + 覆盖率
    qa = set(_build_tokens(q))
    qb = set(_build_tokens(cand))
    if not qa or not qb:
        return 0.0
    inter = len(qa & qb)
    union = len(qa | qb)
    jacc = inter / union
    cover = inter / len(qb)
    return 0.6 * jacc + 0.4 * cover

def _color_score(a: str, b: str) -> float:
    """
    颜色相似度：
      完全相等(清洗后) = 1.0；词元包含 = 0.9；词元有交集 = 0.6；否则 = 0
    """
    ca = _clean_color_text(a).lower()
    cb = _clean_color_text(b).lower()
    if ca and cb and ca == cb:
        return 1.0
    sa = _color_tokens(a)
    sb = _color_tokens(b)
    if not sa or not sb:
        return 0.0
    if sa.issubset(sb) or sb.issubset(sa):
        return 0.9
    if sa & sb:
        return 0.6
    return 0.0

def _type_score(q_name: str, cand_name: str) -> float:
    return 1.0 if (_type_tokens(q_name) & _type_tokens(cand_name)) else 0.0


# ======== 候选召回（SQL by psycopg2） ========

def _fetch_candidates_by_color(conn, color_text: str) -> List[Candidate]:
    """颜色宽松召回：等值 / 包含 / 被包含；必要时退到颜色族"""
    color_std = normalize_color_for_match(color_text)
    color_std_l = color_std.lower()

    rows: List[Tuple[str,str,str]] = []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT color_code, style_name, color
            FROM barbour_products
            WHERE lower(color) = %s
               OR lower(color) LIKE %s
               OR %s LIKE ('%%' || lower(color) || '%%')
        """, (color_std_l, f"%{color_std_l}%", color_std_l))
        rows = cur.fetchall()

        # 仍无 → 退到颜色族关键字
        if not rows:
            key = next((k for k in COLOR_FAMILY_KEYS if k in color_std_l), None)
            if key:
                cur.execute("""
                    SELECT DISTINCT color_code, style_name, color
                    FROM barbour_products
                    WHERE lower(color) LIKE %s
                """, (f"%{key}%",))
                rows = cur.fetchall()

    return [Candidate(*r) for r in rows]


# ======== 对外主函数 ========

def resolve_color_code(
    conn,
    product_name: str,
    product_color: str,
    *,
    name_w: float = 0.68,
    color_w: float = 0.27,
    type_w: float = 0.05,
    base_threshold: float = 0.55,
    base_lead: float = 0.10,
    topk_log: int = 5,
) -> MatchResult:
    """
    返回 MatchResult：
      - matched: color_code/score/style_name
      - unmatched: candidates 含 top-K 候选及各分项得分
    """
    candidates = _fetch_candidates_by_color(conn, product_color)
    if not candidates:
        return MatchResult(status="unmatched", candidates=[])

    # 自适应阈值（名称 token 少时放宽；未装 rapidfuzz 时更宽）
    token_cnt = len(_build_tokens(product_name))
    if _HAS_RAPIDFUZZ:
        threshold = base_threshold if token_cnt >= 3 else max(0.45, base_threshold - 0.05)
        lead_delta = base_lead  if token_cnt >= 3 else max(0.05, base_lead - 0.05)
    else:
        threshold = 0.48 if token_cnt >= 3 else 0.45
        lead_delta = 0.07

    scored = []
    for c in candidates:
        s_name = _name_score(product_name, c.style_name)
        s_col  = _color_score(product_color, c.color)
        s_typ  = _type_score(product_name, c.style_name)
        total  = round(name_w * s_name + color_w * s_col + type_w * s_typ, 4)
        scored.append((c.color_code, c.style_name, c.color, s_name, s_col, s_typ, total))

    scored.sort(key=lambda x: x[6], reverse=True)
    best = scored[0]

    # 高分时放宽唯一性要求（避免“第二名很高”卡住）
    if best[6] >= 0.92:
        lead_delta = min(lead_delta, 0.05)

    # 唯一性判定
    if best[6] >= threshold and (len(scored) == 1 or best[6] - scored[1][6] >= lead_delta):
        return MatchResult(status="matched", color_code=best[0], style_name=best[1], score=best[6])

    # === 强规则兜底：query token 被候选覆盖 + 颜色相容 + 类型一致 → 直接通过 ===
    qtok = set(_build_tokens(product_name))
    if qtok:
        for cc, st, dbcol, nsc, csc, tsc, total in scored[:3]:
            stok = set(_build_tokens(st))
            if qtok.issubset(stok) and _color_score(product_color, dbcol) >= 0.6 and _type_score(product_name, st) >= 0.99:
                return MatchResult(status="matched", color_code=cc, style_name=st, score=total)

    # 仍打平 → 若类型和名称几乎完全一致，直接选（保留原逻辑）
    if len(scored) >= 2:
        bt = _type_tokens(product_name)
        for cand in scored[:2]:
            if bt & _type_tokens(cand[1]) and _name_score(product_name, cand[1]) >= 0.99:
                return MatchResult(status="matched", color_code=cand[0], style_name=cand[1], score=cand[6])

    return MatchResult(status="unmatched", candidates=scored[:topk_log])


# ======== 便捷：打印调试日志（可选） ========

def debug_log(name: str, color: str, res: MatchResult, printer: Callable[[str], None] = print) -> None:
    if res.status == "matched":
        printer(f"✅ 匹配成功：{res.color_code} | {res.style_name} | score={res.score}")
    else:
        printer(f"🟡 模糊匹配未达阈值或不唯一：name='{name}', color='{color}'")
        for i, (cc, st, dbcol, nsc, csc, tsc, sc) in enumerate(res.candidates or [], 1):
            printer(f"   候选{i}: {cc} | {st} | color='{dbcol}' | name={round(nsc,4)} color={round(csc,4)} type={round(tsc,4)} score={round(sc,4)}")
