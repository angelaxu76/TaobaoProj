# -*- coding: utf-8 -*-
"""
common_taobao/matching/hybrid_barbour_matcher.py

目标：把“匹配决策过程”独立成可复用模块，供 HOF / OutdoorAndCountry / Allweathers / PMD 等站点共用。

匹配顺序（可调）：
  0) manual mapping（可选：manage_unmatched_candidates.find_code_by_site_url）
  1) URL→Code cache（可选：由站点脚本构建）
  2) 颜色+标题模糊匹配（match_resolver / sim_matcher）
  3) L1/L2 词库匹配（keyword_lexicon + barbour_products.match_keywords_l1/l2）
  4) sku_guess 兜底

返回：(product_code 或 None, debug_trace)
debug_trace 会把每一步的输入/命中/失败原因写全，方便你提升匹配率。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List
import json
import re
import unicodedata

# --- 复用：颜色标准化 ---
try:
    from brands.barbour.core.color_utils import normalize_color as _normalize_color
except Exception:
    _normalize_color = None

# --- 复用：简单颜色清洗（跨站点比较用） ---
try:
    from brands.barbour.core.color_norm import norm_color as _norm_color
except Exception:
    _norm_color = None

# --- 复用：通用颜色+名称 resolver（你已有，里面会调用 match_resolver）---
try:
    from brands.barbour.core.color_code_resolver import find_color_code_by_keywords
except Exception:
    find_color_code_by_keywords = None

# --- 复用：sim_matcher（你已有，三维打分很稳）---
try:
    from brands.barbour.core.sim_matcher import match_product as sim_match_product
    from brands.barbour.core.sim_matcher import choose_best as sim_choose_best
except Exception:
    sim_match_product = None
    sim_choose_best = None

# --- 可选：人工映射 ---
try:
    from brands.barbour.common.manage_unmatched_candidates import find_code_by_site_url
except Exception:
    find_code_by_site_url = None


def _normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _tokenize_simple(text: str) -> List[str]:
    t = _normalize_ascii(text).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return [w for w in t.split() if len(w) >= 3]


def _dedupe_keep_order(words: List[str]) -> List[str]:
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _sql_ident(name: str) -> str:
    # 极简 identifier 清洗（防 SQL 注入；表名来自 config 但仍防一下）
    return re.sub(r"[^a-zA-Z0-9_]", "", name or "")


def normalize_color_for_site(color: str) -> str:
    """
    站点颜色经常带色码：'Olive OL71' / 'Navy NY91' / 'Black BK11'
    这里把色码剥离，并可选调用全局 normalize_color 做别名收敛。
    """
    if not color or color == "No Data":
        return ""
    c = color.strip()
    c = re.sub(r"\s+[A-Z]{1,3}\d{2,3}\b", "", c).strip()
    c = c.split("/")[0].strip()
    c = re.sub(r"[^A-Za-z\s]", " ", c).strip()
    c = re.sub(r"\s+", " ", c)
    if _normalize_color:
        try:
            return (_normalize_color(c) or c).strip().lower()
        except Exception:
            return c.lower()
    return c.lower()


def resolve_by_partial_code(
    raw_conn,
    partial_code: str,
    scraped_color: str,
    products_table: str = "barbour_products",
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    当网站只提供截断编码（如 LQU0475，7 位无颜色后缀）时：
    1. SELECT product_code, color FROM barbour_products WHERE product_code ILIKE 'LQU0475%'
    2. 用 norm_color 对比颜色，精确匹配对应色号的完整编码
    3. 如果只有一个候选，直接返回（无需颜色比较）

    Returns:
        (product_code 或 None, debug_dict)
    """
    dbg: Dict[str, Any] = {
        "stage": "partial_code",
        "partial_code": partial_code,
        "scraped_color": scraped_color,
        "candidates": [],
        "reason": "",
    }

    if not partial_code or len(partial_code) < 7:
        dbg["reason"] = "SKIP_TOO_SHORT"
        return None, dbg

    tbl = _sql_ident(products_table) or "barbour_products"

    # 查询所有以 partial_code 为前缀的 product_code
    sql = f"""
        SELECT DISTINCT product_code, color
        FROM {tbl}
        WHERE product_code ILIKE %s
    """
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql, (f"{partial_code}%",))
            rows = cur.fetchall()
    except Exception as e:
        dbg["reason"] = f"DB_ERROR: {e}"
        try:
            raw_conn.rollback()
        except Exception:
            pass
        return None, dbg

    if not rows:
        dbg["reason"] = "NO_CANDIDATES"
        return None, dbg

    # 去重：按 product_code 分组
    candidates = {}
    for code, color in rows:
        if code not in candidates:
            candidates[code] = color or ""

    dbg["candidates"] = [{"code": c, "color": clr} for c, clr in candidates.items()]

    # 只有一个候选 → 直接返回
    if len(candidates) == 1:
        code = next(iter(candidates))
        dbg["reason"] = "UNIQUE_MATCH"
        return code, dbg

    # 多个候选 → 用颜色比较
    norm_func = _norm_color or (lambda x: (x or "").strip().lower().split("/")[0].split()[0] if x else "")
    scraped_norm = norm_func(scraped_color)

    if not scraped_norm:
        dbg["reason"] = "NO_COLOR_TO_COMPARE"
        return None, dbg

    matched = []
    for code, db_color in candidates.items():
        db_norm = norm_func(db_color)
        if scraped_norm == db_norm:
            matched.append(code)

    if len(matched) == 1:
        dbg["reason"] = "COLOR_MATCHED"
        return matched[0], dbg

    if len(matched) > 1:
        # 多个颜色匹配（不应该发生，但兜底取第一个）
        dbg["reason"] = "MULTI_COLOR_MATCH"
        return matched[0], dbg

    dbg["reason"] = "COLOR_MISMATCH"
    return None, dbg


def load_lexicon_set(raw_conn, brand: str, level: int) -> set[str]:
    brand = (brand or "barbour").strip().lower()
    lvl = int(level)
    sql = """
      SELECT keyword
      FROM keyword_lexicon
      WHERE brand=%s AND level=%s AND is_active=true
    """
    with raw_conn.cursor() as cur:
        cur.execute(sql, (brand, lvl))
        return {str(r[0]).strip().lower() for r in cur.fetchall() if r and r[0]}


def hits_by_lexicon(text: str, lex_set: set[str]) -> List[str]:
    tokens = _tokenize_simple(text)
    hits = [w for w in tokens if w in lex_set]
    return _dedupe_keep_order(hits)


def _saturating_score(k: int) -> float:
    # 0->0, 1->0.75, 2->0.90, >=3->1.0
    if k <= 0:
        return 0.0
    if k == 1:
        return 0.75
    if k == 2:
        return 0.90
    return 1.0


def match_by_lexicon(
    raw_conn,
    *,
    products_table: str,
    brand: str,
    scraped_title: str,
    scraped_color: str,
    recall_limit: int = 3000,
    topk: int = 25,
    min_l1_hits: int = 1,
    require_color_exact: bool = False,
    # weights
    w_l1: float = 0.55,
    w_l2: float = 0.20,
    w_color: float = 0.10,
    w_name_sim: float = 0.15,   # ★ 新增：避免“同色不同款”打平
    min_score: float = 0.68,
    min_lead: float = 0.04,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Lexicon 匹配（增强版）：
      - L1 召回：match_keywords_l1 && scraped_l1
      - 候选打分：L1 overlap + L2 overlap + 颜色相等 + （新增）名称相似度 name_sim
    """
    dbg: Dict[str, Any] = {
        "stage": "lexicon",
        "scraped_title": scraped_title,
        "scraped_color": scraped_color,
        "scraped_color_norm": normalize_color_for_site(scraped_color),
        "scraped_l1": [],
        "scraped_l2": [],
        "candidates": 0,
        "top": [],
        "reason": "",
    }

    tbl = _sql_ident(products_table) or "barbour_products"
    l1_set = load_lexicon_set(raw_conn, brand, 1)
    l2_set = load_lexicon_set(raw_conn, brand, 2)

    scraped_l1 = hits_by_lexicon(scraped_title or "", l1_set)
    scraped_l2 = hits_by_lexicon(scraped_title or "", l2_set)

    dbg["scraped_l1"] = scraped_l1
    dbg["scraped_l2"] = scraped_l2

    if len(scraped_l1) < min_l1_hits:
        dbg["reason"] = "FAIL_NO_L1"
        return None, dbg

    sql = f"""
    SELECT DISTINCT ON (product_code, color)
        product_code,
        style_name,
        color,
        match_keywords_l1,
        match_keywords_l2,
        source_rank
    FROM {tbl}
    WHERE match_keywords_l1 && %s::text[]
    ORDER BY product_code, color, source_rank ASC
    LIMIT %s
    """
    with raw_conn.cursor() as cur:
        cur.execute(sql, (scraped_l1, int(recall_limit)))
        rows = cur.fetchall()

    dbg["candidates"] = len(rows)
    if not rows:
        dbg["reason"] = "FAIL_NO_CANDIDATE"
        return None, dbg

    color_q = dbg["scraped_color_norm"]
    has_color = bool(color_q)

    # 用 sim_matcher 的 name_sim（如果可用）给一个 name_sim 分，没装 rapidfuzz 也有降级
    name_sim_func = None
    try:
        from brands.barbour.core.sim_matcher import name_sim as _ns
        name_sim_func = _ns
    except Exception:
        name_sim_func = None

    scored = []
    for (product_code, style_name, color_db, kw_l1, kw_l2, source_rank) in rows:
        cand_l1 = list(kw_l1 or [])
        cand_l2 = list(kw_l2 or [])
        cand_color = normalize_color_for_site(color_db or "")

        l1_overlap = len(set(cand_l1) & set(scraped_l1))
        l2_overlap = len(set(cand_l2) & set(scraped_l2)) if scraped_l2 else 0

        color_match = 0.0
        if has_color and cand_color:
            color_match = 1.0 if cand_color == color_q else 0.0

        if require_color_exact and has_color and color_match < 1.0:
            continue

        ns = 0.0
        if name_sim_func:
            try:
                ns = float(name_sim_func(scraped_title or "", style_name or ""))  # 0..1
            except Exception:
                ns = 0.0

        score = (
            w_l1 * _saturating_score(l1_overlap)
            + w_l2 * _saturating_score(l2_overlap)
            + w_color * color_match
            + w_name_sim * ns
        )

        scored.append({
            "product_code": product_code,
            "style_name": style_name,
            "color": color_db,
            "cand_color_norm": cand_color,
            "l1_overlap": l1_overlap,
            "l2_overlap": l2_overlap,
            "color_match": color_match,
            "name_sim": round(ns, 4),
            "score": round(score, 4),
            "source_rank": source_rank,
        })

    if not scored:
        dbg["reason"] = "FAIL_AFTER_COLOR_FILTER"
        return None, dbg

    scored.sort(key=lambda x: (x["score"], x["l1_overlap"], x["l2_overlap"]), reverse=True)
    dbg["top"] = scored[:topk]

    best = dbg["top"][0]
    second = dbg["top"][1] if len(dbg["top"]) >= 2 else None

    if best["score"] < float(min_score):
        dbg["reason"] = "FAIL_LOW_SCORE"
        return None, dbg

    if second is not None and (best["score"] - second["score"]) < float(min_lead):
        dbg["reason"] = "FAIL_LOW_LEAD"
        return None, dbg

    dbg["reason"] = "OK"
    return best["product_code"], dbg


def resolve_product_code(
    raw_conn,
    *,
    site_name: str,
    url: str,
    scraped_title: str,
    scraped_color: str,
    sku_guess: Optional[str],
    partial_code: Optional[str] = None,    # ★ 截断编码 (如 LQU0475)
    products_table: str = "barbour_products",
    offers_table: Optional[str] = None,   # 站点脚本可不用传
    url_code_cache: Optional[Dict[str, str]] = None,
    brand: str = "barbour",
    debug: bool = True,
    # --- sim_matcher 阈值 ---
    sim_min_score: float = 0.72,
    sim_min_lead: float = 0.04,
    # --- lexicon 参数 ---
    lex_min_l1_hits: int = 1,
    lex_min_score: float = 0.68,
    lex_min_lead: float = 0.04,
    lex_require_color_exact: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """
    统一解析入口：返回 (final_code, debug_trace)

    debug_trace:
      { "steps": [ {stage, status, ...}, ... ], "final": {code, by} }
    """
    trace: Dict[str, Any] = {"site": site_name, "url": url, "steps": [], "final": {}}

    norm_url = (url or "").strip()

    # 0) 人工映射（如果你有）
    if find_code_by_site_url:
        try:
            manual = find_code_by_site_url(raw_conn, site_name, norm_url)
            if manual:
                trace["steps"].append({"stage": "manual", "status": "hit", "code": manual})
                trace["final"] = {"code": manual, "by": "manual"}
                return manual, trace
            trace["steps"].append({"stage": "manual", "status": "miss"})
        except Exception as e:
            trace["steps"].append({"stage": "manual", "status": "error", "error": str(e)})

    # 1) URL cache
    if url_code_cache is not None:
        cached = url_code_cache.get(norm_url)
        if cached:
            trace["steps"].append({"stage": "url_cache", "status": "hit", "code": cached})
            trace["final"] = {"code": cached, "by": "url_cache"}
            return cached, trace
        trace["steps"].append({"stage": "url_cache", "status": "miss"})

    # 1.5) ★ 截断编码 + 颜色匹配（如 LQU0475 → LQU0475OL71）
    if partial_code and len(partial_code) >= 7:
        try:
            pc_result, pc_dbg = resolve_by_partial_code(
                raw_conn,
                partial_code=partial_code,
                scraped_color=scraped_color or "",
                products_table=products_table,
            )
            trace["steps"].append({
                "stage": "partial_code",
                "status": "hit" if pc_result else "miss",
                "detail": pc_dbg,
            })
            if pc_result:
                trace["final"] = {"code": pc_result, "by": "partial_code"}
                return pc_result, trace
        except Exception as e:
            trace["steps"].append({"stage": "partial_code", "status": "error", "error": str(e)})

    # 2) 颜色+标题模糊匹配（优先用你已有的 color_code_resolver，它内部有详细 debug）
    if find_color_code_by_keywords:
        try:
            cc = find_color_code_by_keywords(
                raw_conn,
                style_name=scraped_title or "",
                color=scraped_color or "",
                products_table=products_table,
                brand=brand,
                supplier=site_name,
                debug=False,
            )
            if cc:
                trace["steps"].append({"stage": "color_code_resolver", "status": "hit", "code": cc})
                trace["final"] = {"code": cc, "by": "color_code_resolver"}
                return cc, trace
            trace["steps"].append({"stage": "color_code_resolver", "status": "miss"})
        except Exception as e:
            trace["steps"].append({"stage": "color_code_resolver", "status": "error", "error": str(e)})

    # 3) Lexicon（增强版 + 可 debug）
    try:
        best, dbg = match_by_lexicon(
            raw_conn,
            products_table=products_table,
            brand=brand,
            scraped_title=scraped_title or "",
            scraped_color=scraped_color or "",
            min_l1_hits=lex_min_l1_hits,
            require_color_exact=lex_require_color_exact,
            min_score=lex_min_score,
            min_lead=lex_min_lead,
        )
        trace["steps"].append({"stage": "lexicon", "status": "hit" if best else "miss", "detail": dbg})
        if best:
            trace["final"] = {"code": best, "by": "lexicon"}
            return best, trace
    except Exception as e:
        trace["steps"].append({"stage": "lexicon", "status": "error", "error": str(e)})

    # 4) sim_matcher（兜底：不依赖 match_keywords_l1/l2）
    if sim_match_product and sim_choose_best:
        try:
            results = sim_match_product(
                raw_conn,
                scraped_title=scraped_title or "",
                scraped_color=scraped_color or "",
                table=products_table,
                topk=5,
                recall_limit=2000,
                min_name=0.92,
                min_color=0.0,
                require_color_exact=False,
                require_type=False,
            )
            code = sim_choose_best(results, min_score=sim_min_score, min_lead=sim_min_lead)
            trace["steps"].append({
                "stage": "sim_matcher",
                "status": "hit" if code else "miss",
                "top": results,
                "min_score": sim_min_score,
                "min_lead": sim_min_lead,
            })
            if code:
                trace["final"] = {"code": code, "by": "sim_matcher"}
                return code, trace
        except Exception as e:
            trace["steps"].append({"stage": "sim_matcher", "status": "error", "error": str(e)})

    # 5) sku_guess
    sku = (sku_guess or "").strip()
    if sku and sku != "No Data":
        trace["steps"].append({"stage": "sku_guess", "status": "hit", "code": sku})
        trace["final"] = {"code": sku, "by": "sku_guess"}
        return sku, trace

    trace["final"] = {"code": "No Data", "by": "none"}
    return "No Data", trace


def dump_debug_trace(trace: Dict[str, Any], path, *, ensure_ascii: bool = False):
    """把 debug trace 写成 json，便于你 diff/统计失败原因。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=ensure_ascii, indent=2)
