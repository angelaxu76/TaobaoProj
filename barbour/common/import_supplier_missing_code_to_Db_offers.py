# -*- coding: utf-8 -*-
"""
专用导入：处理“TXT 没有 product_code”的报价
- 只要匹配到编码才入库；匹配不到写 missing CSV
- 匹配顺序：颜色 LIKE 过滤 → 关键词命中计分 →（兜底）RapidFuzz 模糊匹配
- 供 pipeline 调用：run_missing_offers_import(brand, suppliers=None, debug=False, rf_threshold=85, rf_margin=5, topk=3)
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
from barbour.common.import_supplier_to_db_offers import parse_txt  # :contentReference[oaicite:1]{index=1}

# RapidFuzz（可选）
try:
    from rapidfuzz import fuzz
    _HAS_RF = True
except Exception:
    fuzz = None
    _HAS_RF = False

# ----------------- 日志 -----------------
logger = logging.getLogger("missing_code_import")

# ----------------- 文本处理 -----------------
STOPWORDS = {
    "the","and","for","with","men","womens","women","ladies","kids","child","children",
    "jacket","jackets","coat","coats","barbour","by","of","in","on","fit","style",
    "wax","waxed","quilt","quilted","liner","lining","vest","gilet","hood","withhood",
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _tokens(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return [t for t in s.split() if t and t not in STOPWORDS and len(t) >= 3]

def _color_like(color: str) -> str:
    c = (color or "").strip()
    c = c.split("/")[0].strip()
    c = c.split()[0] if c else ""
    return f"%{c.lower()}%" if c else "%"

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
) -> Optional[str]:
    style_name_norm = _norm(style_name)
    color_norm = _norm(color)
    kw = _tokens(style_name_norm)
    color_like = _color_like(color_norm)

    if debug:
        logger.debug("匹配尝试 | kw=%s | color_like=%s", kw, color_like)

    rows = conn.execute(text("""
        SELECT product_code, style_name, color, title
        FROM barbour_products
        WHERE (:color_like = '%' OR LOWER(color) LIKE :color_like)
    """), {"color_like": color_like}).fetchall()

    if debug:
        logger.debug("候选数（按颜色过滤）：%d", len(rows))

    # A) 关键词命中计分
    scores_kw = []
    best_code, best_score, tie = None, 0, False
    for pc, sty, col, title in rows:
        blob = f"{sty or ''} {title or ''}".lower()
        score = sum(1 for t in kw if t in blob)
        if color_norm and color_norm.lower().split()[0] in (str(col or "").lower()):
            score += 1
        scores_kw.append((score, pc))
        if score > best_score:
            best_code, best_score, tie = pc, score, False
        elif score == best_score and score > 0:
            tie = True

    scores_kw.sort(key=lambda x: x[0], reverse=True)
    if debug and scores_kw:
        logger.debug("关键词Top%d：%s", topk, scores_kw[:topk])

    if best_score >= 2 and not tie and best_code:
        if debug:
            logger.debug("✅ 采用（关键词计分）：code=%s | score=%d", best_code, best_score)
        return best_code

    # B) RapidFuzz 兜底
    if _HAS_RF and rows:
        query = " ".join(kw) if kw else style_name_norm.lower()
        scores_rf: List[Tuple[int, str]] = []
        for pc, sty, col, title in rows:
            candidate = f"{sty or ''} {title or ''}".lower()
            scores_rf.append((fuzz.token_set_ratio(query, candidate), pc))
        scores_rf.sort(reverse=True)
        if debug:
            logger.debug("RF Top%d：%s", topk, scores_rf[:topk])
        top_score, top_code = scores_rf[0]
        second = scores_rf[1][0] if len(scores_rf) > 1 else 0
        if top_score >= rf_threshold and (top_score - second) >= rf_margin:
            if debug:
                logger.debug("✅ 采用（RF兜底）：code=%s | score=%d (second=%d)", top_code, top_score, second)
            return top_code
        if debug:
            logger.debug("❌ RF未通过阈值：top=%d second=%d threshold=%d margin=%d",
                         top_score, second, rf_threshold, rf_margin)

    if debug:
        logger.debug("❌ 放弃：未达阈值或并列最高分")
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
            rf_threshold=rf_threshold, rf_margin=rf_margin, topk=topk, debug=debug
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
            info = parse_txt(p)  # 读 TXT → dict（沿用你的解析函数） :contentReference[oaicite:2]{index=2}

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
