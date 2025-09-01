# common_taobao/matching/color_code_resolver.py
# -*- coding: utf-8 -*-
"""
通用：颜色+款名 → color_code（product_code）解析器入口
- 对外：find_color_code_by_keywords(conn, style_name, color, ...)
- 内部：调用你现有的高级匹配器 resolve_color_code（支持 RapidFuzz / 无依赖降级）
- 可共享给所有 fetch_info（Allweathers / Outdoor & Country / PMD / HOF / HoF 等）

依赖（可选增强）：
- match_resolver.resolve_color_code / debug_log        (你已上传)  :contentReference[oaicite:3]{index=3}
- color_utils.normalize_color (颜色标准化、别名映射)        (你已上传)  :contentReference[oaicite:4]{index=4}
- keyword_mapping.KEYWORD_EQUIVALENTS (等价词库，可扩展)   (你已上传)  :contentReference[oaicite:5]{index=5}
"""
from __future__ import annotations  # ★ 必须在最前（仅允许注释/文档字符串在它前面）
import re
from dataclasses import asdict
from typing import Optional, Tuple
from barbour.core.color_utils import normalize_color
from barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS
from barbour.core.match_resolver import resolve_color_code, debug_log
import barbour.core.match_resolver as _mr

# -*- coding: utf-8 -*-
"""Product code resolver: normalize name/color, strip stopwords, and resolve product_code via DB."""



import re  # ★ 你停用词正则会用到它
from dataclasses import asdict
from typing import Optional, Tuple

# 可选依赖：颜色规范化
try:
    from barbour.core.color_utils import normalize_color
except Exception:
    normalize_color = None

# 关键词等价 & 停用词（集中维护处）
try:
    from barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS, STOPWORDS as _KM_STOPWORDS
except Exception:
    KEYWORD_EQUIVALENTS = None
    _KM_STOPWORDS = None

# 核心匹配器（不要在站点脚本里直接用它；统一走 find_color_code_by_keywords）
from barbour.core.match_resolver import resolve_color_code, debug_log

# --- 可选：读取你已有的颜色/关键词工具（存在则自动使用，不存在也不报错） ---

try:
    from barbour.core.keyword_mapping import STOPWORDS as _KM_STOPWORDS
except Exception:
    _KM_STOPWORDS = None


FORCE_KEEP = {"quilted", "wax", "waxed"}

# 默认停用词（你提到的都在这里；可按需增减）
_DEFAULT_STOPWORDS = {
    "barbour", "international", "jacket", "waterproof",
    "coat", "coats", "overshirt",  # 这些通常也没区分度；不想排除就删掉
    "men", "mens", "women", "womens", "kids", "boys", "girls"
}

def _get_stopwords():
    sw = set(_DEFAULT_STOPWORDS)
    if _KM_STOPWORDS:
        # keyword_mapping 里定义的优先（集中维护）
        sw = set(_KM_STOPWORDS)
    # 强制保留从停用词中移除
    return {w for w in sw if w not in FORCE_KEEP}

def _strip_stopwords(text: str) -> str:
    """把停用词从款名里删除（不动 'quilted'/'waxed' 等关键差异词）"""
    s = text or ""
    stopwords = _get_stopwords()
    if not stopwords:
        return s
    for w in stopwords:
        s = re.sub(rf"\b{re.escape(w)}\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()

def _normalize_inputs(style_name: str, color_text: str) -> Tuple[str, str]:
    """轻度清洗：去空格/换行；颜色可选标准化。"""
    s = (style_name or "").strip()
    c = (color_text or "").strip()
    if normalize_color:
        try:
            c = normalize_color(c) or c
        except Exception:
            pass
    return s, c


def find_color_code_by_keywords(
    conn,
    style_name: str,
    color: str,
    *,
    products_table: str = "barbour_products",
    brand: str = "barbour",
    supplier: str = "",
    debug: bool = False,
    # 新参数（推荐使用）
    name_weight: float = 0.68,
    color_weight: float = 0.27,
    type_weight: float = 0.05,
    base_threshold: float = 0.55,
    base_lead: float = 0.10,
    # ↓↓↓ 兼容旧参数（允许传入但不会报错）
    **kwargs,
) -> Optional[str]:
    """
    兼容参数：
      - rf_threshold: 0..100 → 近似映射为 base_threshold（0..1）
      - rf_margin:    0..100 → 近似映射为 base_lead（0..1）
    """
    # ---- 兼容旧参数名 ----
    rf_threshold = kwargs.pop("rf_threshold", None)
    rf_margin    = kwargs.pop("rf_margin", None)
    if rf_threshold is not None:
        try:
            # 旧 rf 是“最小相似度百分比”；我们把它保守地映射为 0.01*rf - 0.10 的基线阈值（最低 0.45）
            base_threshold = max(base_threshold, max(0.45, min(0.90, float(rf_threshold) / 100.0 - 0.10)))
        except Exception:
            pass
    if rf_margin is not None:
        try:
            # 旧 rf_margin 是“前两名分差百分比”；映射为 0.01*rf_margin 的领先幅度（范围 0.02~0.20）
            base_lead = max(base_lead, max(0.02, min(0.20, float(rf_margin) / 100.0)))
        except Exception:
            pass
    # 避免用户传了其他未知参数而报错
    if kwargs:
        # 仅在 debug 时提示
        if debug:
            print(f"[color_code_resolver] 忽略未识别参数: {list(kwargs.keys())}")

    # 轻清洗/标准化
    q_name, q_color = _normalize_inputs(style_name, color)
    # ★ 停用词过滤 —— 去掉 international/jacket/waterproof 等通用词
    q_name = _strip_stopwords(q_name)


    # --- 注入自定义表名（保留你现有 match_resolver 的 SQL 结构） ---

    _orig_fetch = getattr(_mr, "_fetch_candidates_by_color")

    def _fetch_with_table(conn_in, color_text_in):
        from typing import List, Tuple
        from barbour.core.match_resolver import Candidate, normalize_color_for_match, COLOR_FAMILY_KEYS  # type: ignore
        color_std = normalize_color_for_match(color_text_in)
        color_std_l = color_std.lower()

        rows: list[Tuple[str, str, str]] = []
        with conn_in.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT product_code, style_name, color
                FROM {products_table}
                WHERE lower(color) = %s
                   OR lower(color) LIKE %s
                   OR %s LIKE ('%%' || lower(color) || '%%')
            """, (color_std_l, f"%{color_std_l}%", color_std_l))
            rows = cur.fetchall()

            if not rows:
                key = next((k for k in COLOR_FAMILY_KEYS if k in color_std_l), None)
                if key:
                    cur.execute(f"""
                        SELECT DISTINCT product_code, style_name, color
                        FROM {products_table}
                        WHERE lower(color) LIKE %s
                    """, (f"%{key}%",))
                    rows = cur.fetchall()

        return [Candidate(*r) for r in rows]

    setattr(_mr, "_fetch_candidates_by_color", _fetch_with_table)
    try:
        res = _mr.resolve_color_code(
            conn,
            product_name=q_name,
            product_color=q_color,
            name_w=name_weight,
            color_w=color_weight,
            type_w=type_weight,
            base_threshold=base_threshold,
            base_lead=base_lead,
            topk_log=5 if debug else 0,
        )
        if debug:
            _mr.debug_log(q_name, q_color, res)
        return res.color_code if res.status == "matched" else None
    finally:
        setattr(_mr, "_fetch_candidates_by_color", _orig_fetch)
