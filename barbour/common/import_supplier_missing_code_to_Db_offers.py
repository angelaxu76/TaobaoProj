# -*- coding: utf-8 -*-
"""
专用导入：处理“TXT 没有 product_code”的报价（覆盖版）
- 只要匹配到编码才入库；匹配不到写 missing CSV
- 匹配顺序：颜色(词+颜色码)过滤 → 关键词命中计分(颜色码高权重) →（兜底）RapidFuzz 模糊匹配
- 供 pipeline 调用：run_missing_offers_import(brand, suppliers=None, debug=False, rf_threshold=85, rf_margin=5, topk=3)

变更要点：
1) 保留 quilted/waxed/padded/leather 等区分款式关键词，不纳入停用词；
2) 解析颜色码（如 BK11/BE51...），参与 SQL 过滤 & 关键词计分 & RF；颜色码权重 +5，颜色词权重 +2；
3) 候选文本增补 color 与 product_code，去除站点词等噪音。
"""

from __future__ import annotations
import re
import csv
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

# 你的项目配置
from config import BRAND_CONFIG
from barbour.core.site_utils import canonical_site, assert_site_or_raise

# 复用你已有的 TXT 解析逻辑（不改动原文件）
from barbour.common.import_supplier_to_db_offers import parse_txt  # 保持不变（外部已有）  :contentReference[oaicite:1]{index=1}

# RapidFuzz（可选）
try:
    from rapidfuzz import fuzz
    _HAS_RF = True
except Exception:
    fuzz = None
    _HAS_RF = False

# ----------------- 日志 -----------------
logger = logging.getLogger("missing_code_import")

# ----------------- 停用词与文本处理 -----------------
# 注意：不要把 quilted / waxed / padded / leather 放入停用词，它们用于区分款式
GLOBAL_STOPWORDS = {
    # 通用低区分度词
    "the","and","for","with","by","of","in","on",
    "men","mens","women","womens","ladies","kid","kids","child","children",
    "uk","official","sale","new","season",
    # 泛类目词（无区分度）
    "jacket","jackets","coat","coats","gilet","gilets","vest","vests","outerwear",
    # 品牌/渠道噪音
    "barbour","barbourinternational","international",
    "frasers","house","houseoffraser","hof",
    "allweather","allweathers",
    "outdoorandcountry","outdoor","oandc",
    "philipmorris","philipmorrisdirect","pmd",
}

SUPPLIER_STOPWORDS = {
    "houseoffraser": {"fraser","frasers","hof","house","houseoffraser"},
    "outdoorandcountry": {"outdoorandcountry","outdoor","oandc"},
    "allweathers": {"allweather","allweathers"},
    "philipmorrisdirect": {"philipmorris","philipmorrisdirect","pmd"},
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _basic_tokens(s: str) -> List[str]:
    """基础分词：小写、去符号、按空白切割"""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return [t for t in s.split() if t]

def _filter_tokens(tokens: List[str], supplier: Optional[str] = None) -> List[str]:
    """移除全局停用词 + 站点停用词；保留 quilted / waxed / padded / leather 等区分词"""
    sw = set(GLOBAL_STOPWORDS)
    if supplier and supplier.lower() in SUPPLIER_STOPWORDS:
        sw |= SUPPLIER_STOPWORDS[supplier.lower()]
    return [t for t in tokens if t and t not in sw]

# 颜色码：如 BK11, BE51, GN91, OL71, NY51...
_COLOR_CODE_RE = re.compile(r"\b([A-Z]{2}\d{2})\b", re.I)

def _split_color_tokens(color: str) -> Tuple[str, str]:
    """
    返回 (颜色词, 颜色码)；任一不存在则返回 ""。
    例：'Black BK11' -> ('black', 'bk11')；'Brindle BE51' -> ('brindle','be51')
    """
    s = (color or "").strip()
    word = ""
    if s:
        word = (s.split("/")[0].strip().split() or [""])[0].lower()
    m = _COLOR_CODE_RE.search(s)
    code = (m.group(1) or "").lower() if m else ""
    return word, code

def _color_likes(color: str) -> Tuple[str, str]:
    """构造 SQL LIKE 参数：(颜色词LIKE, 颜色码LIKE)"""
    w, c = _split_color_tokens(color)
    like_word = f"%{w}%" if w else "%"
    like_code = f"%{c}%" if c else "%"
    return like_word, like_code

# ----------------- 匹配编码 -----------------
def find_color_code_by_keywords(
    conn: Connection,
    style_name: str,
    color: str,
    *,
    rf_threshold: int = 85,
    rf_margin: int = 5,
    topk: int = 3,
    debug: bool = False,
    supplier: Optional[str] = None,
) -> Optional[str]:
    style_name_norm = _norm(style_name)
    color_norm = _norm(color)

    # === 构建关键词（含颜色词/颜色码），并做停用词过滤 ===
    kw_raw = _basic_tokens(style_name_norm)
    w_color, c_color = _split_color_tokens(color_norm)
    if w_color: kw_raw.append(w_color)
    if c_color: kw_raw.append(c_color)
    kw = _filter_tokens(kw_raw, supplier=supplier)

    like_word, like_code = _color_likes(color_norm)
    if debug:
        logger.debug("匹配尝试 | kw=%s | color_like_word=%s | color_like_code=%s", kw, like_word, like_code)

    rows = conn.execute(text("""
        SELECT product_code, style_name, color, title
        FROM barbour_products
        WHERE
          (:like_word = '%' OR LOWER(color) LIKE :like_word)
          OR (:like_code = '%' OR LOWER(color) LIKE :like_code OR LOWER(product_code) LIKE :like_code)
    """), {"like_word": like_word, "like_code": like_code}).fetchall()

    if debug:
        logger.debug("候选数（按颜色过滤）：%d", len(rows))

    # ========== A) 关键词计分（先按编码聚合“该编码最高分”） ==========
    per_code_kw: Dict[str, int] = {}
    for pc, sty, col, title in rows:
        code = (pc or "").lower()
        blob = f"{sty or ''} {title or ''} {col or ''} {pc or ''}".lower()
        col_l = (col or "").lower()

        score = 0
        if c_color and c_color in blob:   # 颜色码强信号
            score += 5
        if w_color and w_color in col_l:  # 颜色词（仅在 color 字段里）次强
            score += 2
        score += sum(1 for t in kw if t and t in blob)

        if score > per_code_kw.get(code, 0):
            per_code_kw[code] = score

    kw_ranked = sorted(per_code_kw.items(), key=lambda x: x[1], reverse=True)
    if debug and kw_ranked:
        logger.debug("关键词Top%d：%s", topk, kw_ranked[:topk])

    # 无并列 or 明显领先时，直接采用
    if kw_ranked:
        top_code, top_score = kw_ranked[0]
        second_score = kw_ranked[1][1] if len(kw_ranked) > 1 else -1
        if top_score >= 3 and (second_score < top_score):
            if debug:
                logger.debug("✅ 采用（关键词计分聚合）：code=%s | score=%d", top_code, top_score)
            return top_code

    # ========== B) RF 模糊匹配（同样按编码聚合“最高RF分”） ==========
    if _HAS_RF and rows:
        query_raw = " ".join(kw_raw) if kw_raw else style_name_norm.lower()
        query_tokens = _filter_tokens(_basic_tokens(query_raw), supplier=supplier)
        query = " ".join(query_tokens) if query_tokens else query_raw

        per_code_rf: Dict[str, int] = {}
        for pc, sty, col, title in rows:
            code = (pc or "").lower()
            candidate = f"{sty or ''} {title or ''} {col or ''} {pc or ''}".lower()
            s = fuzz.token_set_ratio(query, candidate)
            if s > per_code_rf.get(code, 0):
                per_code_rf[code] = s

        rf_ranked = sorted(per_code_rf.items(), key=lambda x: x[1], reverse=True)
        if debug and rf_ranked:
            logger.debug("RF Top%d：%s", topk, rf_ranked[:topk])

        if rf_ranked:
            top_code, top_score = rf_ranked[0]
            # 如果TopK全是同一编码（聚合后自然只有一个），直接过
            if top_score >= rf_threshold and (len(rf_ranked) == 1):
                if debug:
                    logger.debug("✅ 采用（RF聚合，唯一编码）：code=%s | score=%d", top_code, top_score)
                return top_code

            second_score = rf_ranked[1][1] if len(rf_ranked) > 1 else -1

            # 常规阈值 + 边际
            if top_score >= rf_threshold and (top_score - second_score) >= rf_margin:
                if debug:
                    logger.debug("✅ 采用（RF聚合）：code=%s | score=%d (second=%d)", top_code, top_score, second_score)
                return top_code

            # 兜底：阈值达标但边际不足时，若 Top1 的编码包含颜色码（如 bk11/be51），也放行
            if top_score >= rf_threshold and c_color and c_color in top_code:
                if debug:
                    logger.debug("✅ 采用（RF聚合兜底：颜色码命中）：code=%s | score=%d", top_code, top_score)
                return top_code

        if debug:
            logger.debug("❌ RF未通过（聚合后仍无明显领先）")

    if debug:
        logger.debug("❌ 放弃：未达阈值或并列最高分（聚合后）")
    return None


# ----------------- 入库（仅有编码才写） -----------------
UPSERT_SQL = text("""
INSERT INTO barbour_offers
    (site_name, offer_url, size,
     price_gbp, original_price_gbp, stock_count,
     product_code, first_seen, last_seen, is_active, last_checked)
VALUES (:site_name, :offer_url, :size,
        :price_gbp, :original_price_gbp, :stock_count,
        :product_code, NOW(), NOW(), TRUE, NOW())
ON CONFLICT (site_name, offer_url, size) DO UPDATE SET
    price_gbp          = EXCLUDED.price_gbp,
    original_price_gbp = EXCLUDED.original_price_gbp,
    stock_count        = EXCLUDED.stock_count,
    product_code       = COALESCE(barbour_offers.product_code, EXCLUDED.product_code),
    last_seen          = NOW(),
    is_active          = TRUE,
    last_checked       = NOW()
""")

def insert_only_when_coded(
    conn: Connection,
    info: dict,
    missing_rows: List[Tuple],
    *,
    debug: bool = False,
    rf_threshold: int = 85,
    rf_margin: int = 5,
    topk: int = 3,
) -> int:
    site = assert_site_or_raise(info.get("site") or info.get("url") or "")
    style_name = info.get("style_name") or ""
    color = info.get("color") or ""
    offer_url = info.get("url") or info.get("product_url") or ""

    product_code = _norm(info.get("product_code") or "")
    if not product_code:
        product_code = find_color_code_by_keywords(
            conn, style_name, color,
            rf_threshold=rf_threshold, rf_margin=rf_margin, topk=topk, debug=debug, supplier=site
        )

    if not product_code:
        if debug:
            logger.warning("未匹配到编码 → 记入missing | site=%s | style=%s | color=%s | url=%s",
                           site, style_name, color, offer_url)
        for off in info.get("offers", []):
            missing_rows.append(("", (off.get("size") or ""), site, style_name, color, offer_url))
        return 0

    if debug:
        logger.info("匹配成功 | code=%s | site=%s | style=%s | color=%s", product_code, site, style_name, color)

    affected = 0
    for off in info.get("offers", []):
        size = (off.get("size") or "").strip()
        if not size:
            continue
        conn.execute(UPSERT_SQL, {
            "site_name": site,
            "offer_url": offer_url,
            "size": size,
            "price_gbp": off.get("price_gbp"),
            "original_price_gbp": off.get("original_price_gbp"),
            "stock_count": off.get("stock_count"),
            "product_code": product_code
        })
        affected += 1
    return affected

# ----------------- 发现 TXT -----------------
def iter_txt_files_for_suppliers(txt_dirs: Dict[str, Path], suppliers: List[str] | None) -> List[Path]:
    paths: List[Path] = []
    if not suppliers or suppliers == ["all"]:
        for _, d in txt_dirs.items():
            if d and Path(d).exists():
                paths.extend(sorted(Path(d).glob("*.txt")))
    else:
        for s in suppliers:
            s2 = canonical_site(s) or s
            d = txt_dirs.get(s2)
            if d and Path(d).exists():
                paths.extend(sorted(Path(d).glob("*.txt")))
    return paths

# ----------------- Pipeline 入口 -----------------
def run_missing_offers_import(
    brand: str,
    suppliers: List[str] | None = None,
    *,
    debug: bool = False,
    rf_threshold: int = 85,
    rf_margin: int = 5,
    topk: int = 3,
) -> dict:
    # 简易日志初始化（只配置一次）
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    conf = BRAND_CONFIG[(brand or "").lower()]
    txt_dirs: Dict[str, Path] = conf["TXT_DIRS"]
    publication_dir: Path = Path(conf["PUBLICATION_DIR"])
    pg = conf["PGSQL_CONFIG"]

    paths = iter_txt_files_for_suppliers(txt_dirs, suppliers or ["all"])
    logger.info("发现 TXT 文件：%d 个（brand=%s, suppliers=%s）", len(paths), brand, suppliers or ["all"])
    if not paths:
        return {"brand": brand, "total_txt": 0, "rows_inserted": 0, "missing_count": 0, "missing_csv": None}

    engine = create_engine(
        f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['dbname']}"
    )
    if not _HAS_RF:
        logger.warning("RapidFuzz 未安装，跳过模糊匹配兜底（可选：pip install rapidfuzz）")

    missing_rows: List[Tuple] = []
    total, affected = 0, 0

    with engine.begin() as conn:
        for p in paths:
            total += 1
            info = parse_txt(p)  # 读 TXT → dict（沿用你的解析函数）  :contentReference[oaicite:2]{index=2}

            # 标准化入口字段
            site_raw = (info.get("site") or info.get("Site Name") or "")
            url_raw  = (info.get("url")  or info.get("Source URL")  or "")
            info["site"] = canonical_site(site_raw) or canonical_site(url_raw) or ""
            info["style_name"] = info.get("style_name") or info.get("Product Name") or info.get("name") or ""
            info["color"] = info.get("color") or info.get("Color") or ""

            logger.debug("解析: %s | site=%s | style=%s | color=%s",
                         p.name, info.get("site"), info.get("style_name"), info.get("color"))

            rows = insert_only_when_coded(
                conn, info, missing_rows,
                debug=debug, rf_threshold=rf_threshold, rf_margin=rf_margin, topk=topk
            )
            affected += rows
            logger.debug("→ 写入 %d 行", rows)

    # 输出 missing CSV（仅当有缺失）
    publication_dir.mkdir(parents=True, exist_ok=True)
    csv_path = publication_dir / f"missing_offers_without_code_{brand}.csv"
    if missing_rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["product_code","size","site_name","style_name","color","offer_url"])
            w.writerows(missing_rows)
        logger.info("Missing 清单：%s（共 %d 条）", csv_path, len(missing_rows))
        csv_out = str(csv_path)
    else:
        csv_out = None

    return {
        "brand": brand,
        "total_txt": total,
        "rows_inserted": affected,
        "missing_count": len(missing_rows),
        "missing_csv": csv_out,
    }

if __name__ == "__main__":
    raise SystemExit("请从 pipeline 调用：run_missing_offers_import(brand, suppliers=None, debug=False)")
