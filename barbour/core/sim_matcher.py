# -*- coding: utf-8 -*-
# TaobaoProj/barbour/core/sim_matcher.py
from __future__ import annotations
import re
from typing import List, Dict, Any, Optional

try:
    from rapidfuzz import fuzz  # pip install rapidfuzz
    _HAVE_RF = True
except Exception:
    _HAVE_RF = False

# —— 停用词（名称相似度用，不包含类型词；类型单独打分） ——
STOPWORDS = {
    "barbour","international",
    "men","mens","women","womens","kids","boys","girls", "coat","coats",   # 仍当停用词（不会影响类型分）
}
FORCE_KEEP = {"quilted","wax","waxed","overshirt","gilet"}

# —— 类型词典（同义词→规范类型） ——
TYPE_CANON = {
    "jacket": {"jacket","jackets"},
    "gilet": {"gilet","vest","bodywarmer"},
    "overshirt": {"overshirt","shirt jacket","shacket","over shirt"},
    "fleece": {"fleece","pile"},
    "shirt": {"shirt"},
    "jumper": {"jumper","sweater","knit","pullover"},
    "coat": {"coat","parka"},
    "cap": {"cap","hat"},
}
TYPE_ORDER = ["jacket","gilet","overshirt","fleece","shirt","jumper","coat","cap"]  # 输出时排序

# —— 颜色别名 ——
COLOR_ALIASES = {
    "black":{"black","classic black","jet black"},
    "navy":{"navy","ink","dark navy"},
    "olive":{"olive","sage"},
    "grey":{"grey","gray"},
    "beige":{"beige","stone","sand"},
}

# —— 清洗/规范化 ——
_RE_UPPER = re.compile(r"\b[A-Z]{4,}\b")
_RE_COLORCODE = re.compile(r"\b[a-z]{2}\d{2}\b", re.I)
_RE_BAR = re.compile(r"[|/]+")

RETAILER = r"(FRASERS|HOUSE\s*OF\s*FRASER(S)?|HOF|HOUSEOFFRASER(S)?)"
CATEGORY = r"(COATS?|OUTERWEAR|CLOTHING|APPAREL)"

def _norm_color(c: Optional[str]) -> Optional[str]:
    if not c:
        return None
    c = c.strip().lower()
    if c in {"no","no data","none","null","n/a",""}:
        return None
    c = c.split("/")[0].strip()
    # 去掉 BK11/NY91 等色码，避免 'black bk11' vs 'black' 只给 0.9 分
    c = re.sub(r"\b[a-z]{2}\d{2}\b", " ", c).strip()
    for k,vs in COLOR_ALIASES.items():
        if c==k or c in vs:
            return k
    return c


def _strip_site_noise(s: str) -> str:
    s = _RE_BAR.sub(" ", s or "")
    s = re.sub(RETAILER, " ", s, flags=re.I)
    s = re.sub(CATEGORY, " ", s, flags=re.I)
    s = _RE_UPPER.sub(" ", s)   # FRASERS/HOF 等
    return re.sub(r"\s+"," ", s).strip()

def _strip_color_tokens(s: str, c_norm: Optional[str]) -> str:
    if c_norm: s = re.sub(rf"\b{re.escape(c_norm)}\b", " ", s, flags=re.I)
    s = _RE_COLORCODE.sub(" ", s)  # BK11/NY91
    return re.sub(r"\s+"," ", s).strip()

def _strip_stopwords(s: str) -> str:
    out=[]
    for t in re.split(r"[^a-z0-9]+", (s or "").lower()):
        if not t: continue
        if t in FORCE_KEEP or t not in STOPWORDS: out.append(t)
    return " ".join(out)

def clean_title(title: str, color_norm: Optional[str]) -> str:
    return _strip_stopwords(_strip_color_tokens(_strip_site_noise(title or ""), color_norm))

# —— 系列词（可按需增补） ——
SERIES = {
    "aldon","adams","alicia","abbots","framwell","ariel","outlaw","lark",
    "ledley","sutley","lumley","spey","exmoor","bedale","beadnell","ashby",
    "beaufort","corbridge","powell","cavalry","otterburn","lilian","lorrie",
}
def series_in(text: str) -> set[str]:
    tl=(text or "").lower()
    return {t for t in SERIES if t in tl}

# —— 类型提取（从原始标题/款名提取，不走停用词） ——
def type_token(raw_text: str) -> Optional[str]:
    """
    直接在原始文本上识别类型（只做简单分隔符清理，不做停用词/分类清理），
    防止 'jacket' 被当噪点误删。
    """
    tl = (raw_text or "").lower()
    tl = tl.replace("|", " ").replace("/", " ")
    tl = re.sub(r"\s+", " ", tl)
    for canon, variants in TYPE_CANON.items():
        for v in sorted(variants, key=len, reverse=True):  # 先长词后短词
            if re.search(rf"\b{re.escape(v)}\b", tl):
                return canon
    return None

# —— 相似度 ——
def name_sim(a: str, b: str) -> float:
    a=a.strip(); b=b.strip()
    if not a or not b: return 0.0
    if _HAVE_RF:
        return max(
            fuzz.token_set_ratio(a,b),
            fuzz.token_sort_ratio(a,b),
            fuzz.partial_ratio(a,b)*0.9
        )/100.0
    # 降级：Jaccard
    ta, tb = set(a.split()), set(b.split())
    return len(ta&tb)/len(ta|tb) if ta and tb else 0.0

def color_sim(c1: Optional[str], c2: Optional[str]) -> float:
    if not c1 or not c2: return 0.0
    c1,c2=c1.lower(), c2.lower()
    if c1==c2: return 1.0
    for k,vs in COLOR_ALIASES.items():
        if (c1==k or c1 in vs) and (c2==k or c2 in vs): return 1.0
    if c1 in c2 or c2 in c1: return 0.9
    return 0.0

def type_sim(t1: Optional[str], t2: Optional[str]) -> float:
    if not t1 or not t2: return 0.0
    return 1.0 if t1==t2 else 0.0

# —— DB 召回（不依赖 keyword 字段） ——
def fetch_candidates(conn, table: str, raw_title: str, color_norm: Optional[str], limit: int = 1500):
    t = _strip_site_noise(raw_title or "")
    m = _RE_COLORCODE.search(t)
    code = m.group(0).upper() if m else None
    ser  = sorted(series_in(t))
    kws  = [w for w in _strip_stopwords(t).split() if len(w)>=3][:6]

    where=[]; params={}
    if color_norm:
        where.append("(lower(color) LIKE %(c)s OR %(c)s LIKE ('%%'||lower(color)||'%%'))")
        params["c"]=f"%{color_norm}%"
    if code:
        where.append("product_code ILIKE %(cc)s"); params["cc"]=f"%{code}%"
    if ser:
        ors=[]
        for i,s in enumerate(ser):
            k=f"ser{i}"; ors.append(f"lower(style_name) LIKE %({k})s"); params[k]=f"%{s}%"
        where.append("("+ " OR ".join(ors) +")")
    if kws:
        ands=[]
        for j,w in enumerate(kws):
            k=f"kw{j}"; ands.append(f"lower(style_name) LIKE %({k})s"); params[k]=f"%{w}%"
        where.append("("+ " AND ".join(ands) +")")

    wsql=" AND ".join(where) if where else "TRUE"
    sql=f"""SELECT DISTINCT product_code, style_name, COALESCE(color,'') AS color
            FROM {table} WHERE {wsql} LIMIT {int(limit)}"""
    with conn.cursor() as cur:
        cur.execute(sql, params); rows=cur.fetchall()
    return [{"product_code":r[0], "style_name":r[1] or "", "color":r[2] or ""} for r in rows]

# —— 主函数：名称+颜色+类型 三维打分 ——
def match_product(conn, scraped_title: str, scraped_color: str, *,
                  table="barbour_products",
                  name_weight=0.72, color_weight=0.20, type_weight=0.08,
                  topk=5, recall_limit=1500,
                  # === 新增：可调硬门槛与行为 ===
                  min_name: float | None = None,     # 例：0.95；None 表示不启用阈值
                  min_color: float | None = None,    # 例：0.95；None 表示不启用阈值
                  require_color_exact: bool = False, # True 时要求 color_sim==1.0（等值/同义）
                  require_type: bool = False,        # True 时要求 type_sim==1.0（类型必须一致）
                  series_bonus: float = 0.02,        # 系列词加成（原先写死 0.02）
                  dedupe_by_code: bool = True        # 是否按 product_code 取最高分去重（保持原逻辑）
                  ):
    c_norm=_norm_color(scraped_color)
    t_clean=clean_title(scraped_title, c_norm)
    t_type = type_token(scraped_title)           # 从原始标题提类型（不会受停用词影响）

    cands=fetch_candidates(conn, table, scraped_title, c_norm, limit=recall_limit)
    if not cands:
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT product_code, style_name, COALESCE(color,'') FROM {table} LIMIT 50000")
            cands=[{"product_code":r[0],"style_name":r[1] or "","color":r[2] or ""} for r in cur.fetchall()]

    res=[]
    for r in cands:
        name_db = clean_title(r["style_name"], _norm_color(r["color"]))
        ns=name_sim(t_clean, name_db)
        cs=color_sim(c_norm, _norm_color(r["color"]))
        db_type = type_token(r["style_name"])
        ts=type_sim(t_type, db_type)

        # === 新增：单项硬门槛过滤 ===
        if min_name is not None and ns < min_name:
            continue
        if require_color_exact and cs < 1.0:
            continue
        if min_color is not None and cs < min_color:
            continue
        if require_type and ts < 1.0:
            continue

        # 归一化（权重和=1.0）
        score = name_weight*ns + color_weight*cs + type_weight*ts
        # 系列词轻微加成（可调）
        if series_in(t_clean) & series_in(name_db):
            score += series_bonus

        res.append({
            **r,
            "name_score": round(ns,4),
            "color_score": round(cs,2),
            "type_score": round(ts,2),
            "score": round(score,4),
            "title_clean": t_clean,
            "style_clean": name_db,
            "type_scraped": t_type,
            "type_db": db_type,
        })

    # 同一 product_code 仅保留最高分（可选）
    if dedupe_by_code:
        best_by_code: Dict[str, Dict[str,Any]] = {}
        for r in res:
            code=r["product_code"]
            if code not in best_by_code or r["score"]>best_by_code[code]["score"]:
                best_by_code[code]=r
        uniq=list(best_by_code.values())
    else:
        uniq=res

    uniq.sort(key=lambda x: x["score"], reverse=True)
    return uniq[:topk]


def choose_best(results, min_score=0.72, min_lead=0.04) -> Optional[str]:
    if not results: return None
    a=results[0]
    if a["score"]<min_score: return None
    if len(results)==1: return a["product_code"]
    lead=a["score"]-results[1]["score"]
    return a["product_code"] if lead>=min_lead else None

# —— 调试解释输出 ——
def explain_results(results, min_score: float, min_lead: float) -> str:
    if not results:
        return "（没有候选被召回）", "no candidates"
    lines=[]
    for i,r in enumerate(results,1):
        lines.append(
            f"  {i:>2}. {r['product_code']} | "
            f"name={r['name_score']:.4f} color={r['color_score']:.2f} type={r['type_score']:.2f} "
            f"score={r['score']:.4f} | type[{r['type_db']}] | {r['style_clean']} | color='{r['color']}'"
        )
    best=results[0]
    if best["score"]<min_score:
        reason=f"score<{min_score:.2f}"
    elif len(results)>1 and (best["score"]-results[1]["score"]<min_lead):
        reason=f"lead<{min_lead:.2f} (diff={(best['score']-results[1]['score']):.4f})"
    else:
        reason="ok"
    return "\n".join(lines), reason
