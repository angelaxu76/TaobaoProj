"""
导出【已发布】且含羊绒类材质（wool/cashmere/merino/lambswool/shearling…）商品的最新标题。

- 数据源：品牌 inventory 表（只取有 channel_product_id 的已发布商品），
  含 product_description / product_material / feature 三列；
  Barbour 额外读 barbour_products；本机 TXT 若存在也一并参与判断
- 羊绒判断：common.text.wool_keyword.detect_wool_keyword（规则见 cfg/taobao_title_keyword_config.py）
- 标题：
    鞋类（camper/clarks/ecco/geox） → common.text.generate_taobao_title_v1（已内置羊绒规则）
    Barbour                          → Barbour 标题生成器 + ensure_wool_in_title 后处理
    Toast 等服装                     → 服装/外套标题生成器 + ensure_wool_in_title 后处理
- 输出：一个 Excel：汇总 + 每个品牌一个 sheet（已发布，用于改标题）
        + 「未发布羊绒鞋」sheet（鞋类品牌，附预生成标题，按有货尺码数倒序）
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2

from config import BRAND_CONFIG, BRAND_NAME_MAP, PGSQL_CONFIG
from common.text.wool_keyword import detect_wool_keyword, ensure_wool_in_title

SHOE_BRANDS = {"camper", "clarks", "ecco", "geox"}
BARBOUR_BRANDS = {"barbour"}
APPAREL_BRANDS = {"toast"}


def _gbk_len(s: str) -> int:
    return len((s or "").encode("gbk", errors="ignore"))


def _read_txt(brand: str, code: str) -> str:
    txt_dir = BRAND_CONFIG.get(brand, {}).get("TXT_DIR")
    if not txt_dir:
        return ""
    p = Path(txt_dir) / f"{code}.txt"
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_published(brand: str) -> list[dict]:
    return _load_rows(brand, published=True)


def _load_rows(brand: str, published: bool) -> list[dict]:
    table = BRAND_CONFIG[brand]["TABLE_NAME"]
    with psycopg2.connect(**PGSQL_CONFIG) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
        table_cols = {r[0] for r in cur.fetchall()}
    def _col(name):
        return f"MAX({name})" if name in table_cols else "NULL"
    sql = f"""
        SELECT product_code,
               string_agg(DISTINCT channel_product_id, ',') AS channel_product_id,
               COALESCE(SUM(stock_count), 0)                       AS total_stock,
               COUNT(*) FILTER (WHERE stock_count > 0)              AS sizes_in_stock,
               MAX(product_title)       AS product_title,
               MAX(product_description) AS product_description,
               {_col("color")}               AS color,
               {_col("product_material")}    AS product_material,
               {_col("feature")}             AS feature,
               MAX(gender)              AS gender,
               MAX(style_category)      AS style_category
        FROM {table}
        GROUP BY product_code
        HAVING {"" if published else "NOT "}bool_or(COALESCE(channel_product_id, '') <> '')
        ORDER BY product_code
    """
    with psycopg2.connect(**PGSQL_CONFIG) as conn, conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        if brand in BARBOUR_BRANDS:
            cur.execute("""
                SELECT DISTINCT ON (product_code) product_code, style_name, color, title, product_description
                FROM barbour_products ORDER BY product_code, updated_at DESC NULLS LAST
            """)
            bp = {r[0]: {"style_name": r[1], "color": r[2], "title": r[3], "desc": r[4]} for r in cur.fetchall()}
            for r in rows:
                r["barbour"] = bp.get(r["product_code"], {})
    return rows


def _shoe_content(r: dict, txt: str) -> str:
    if txt:
        return txt
    return "\n".join([
        f"Product Code: {r['product_code']}",
        f"Product Name: {r.get('product_title') or ''}",
        f"Product Description: {r.get('product_description') or ''}",
        f"Product Gender: {r.get('gender') or ''}",
        f"Product Color: {r.get('color') or ''}",
        f"Style Category: {r.get('style_category') or ''}",
        f"Product Material: {r.get('product_material') or ''}",
        f"Feature: {r.get('feature') or ''}",
    ])


def _title_shoe(brand: str, r: dict, content: str) -> str:
    from common.text.generate_taobao_title_v1 import generate_taobao_title
    return generate_taobao_title(r["product_code"], content, brand).get("taobao_title", "")


def _title_barbour(r: dict, wool_cn: str) -> str:
    from brands.barbour.common.generate_taobao_title_v2 import generate_barbour_taobao_title
    from brands.barbour.common.generate_taobao_title_accessories import (
        generate_barbour_accessory_title, is_accessory_code,
    )
    bp = r.get("barbour") or {}
    code = r["product_code"]
    style = bp.get("style_name") or r.get("product_title") or ""
    color = bp.get("color") or r.get("color") or ""
    if is_accessory_code(code):
        info = generate_barbour_accessory_title(code, style, color, description=bp.get("desc"))
    else:
        info = generate_barbour_taobao_title(code, style, color)
    brand_en = BRAND_NAME_MAP.get("barbour", ("Barbour", ""))[0]
    return ensure_wool_in_title(info.get("Title", ""), wool_cn, brand_prefix=brand_en)


def _title_apparel(brand: str, r: dict, content: str, wool_cn: str) -> str:
    from channels.jingya.export.generate_publication_excel_outerwear import (
        determine_category_cn, _title_outerwear, _title_apparel as _gen_apparel,
    )
    code = r["product_code"]
    title_en = r.get("product_title") or ""
    cat_cn = determine_category_cn(r.get("style_category"), title_en, content)
    if cat_cn == "外套":
        t = _title_outerwear(code, content, brand, title_en)
    else:
        t = _gen_apparel(code, content, brand, title_en)
    brand_en = BRAND_NAME_MAP.get(brand, (brand.upper(), ""))[0]
    return ensure_wool_in_title(t, wool_cn, brand_prefix=brand_en)


def collect_wool_titles(brand: str) -> pd.DataFrame:
    brand = brand.lower()
    rows = _load_published(brand)
    out = []
    for r in rows:
        code = r["product_code"]
        txt = _read_txt(brand, code)
        bp = r.get("barbour") or {}
        en_title = bp.get("style_name") or r.get("product_title") or ""
        blob = " ".join(filter(None, [
            r.get("product_description"), r.get("product_material"), r.get("feature"),
            bp.get("title"), bp.get("desc"), txt,
        ]))
        wool_cn = detect_wool_keyword(en_title, blob)
        if not wool_cn:
            continue

        try:
            if brand in SHOE_BRANDS:
                title = _title_shoe(brand, r, _shoe_content(r, txt))
            elif brand in BARBOUR_BRANDS:
                title = _title_barbour(r, wool_cn)
            else:
                content = txt or _shoe_content(r, "")
                title = _title_apparel(brand, r, content, wool_cn)
            err = ""
        except Exception as e:
            title, err = "", str(e)

        out.append({
            "品牌": brand,
            "商品编码": code,
            "渠道产品ID": r.get("channel_product_id") or "",
            "新标题": title,
            "标题字节数": _gbk_len(title),
            "含羊绒": "是" if wool_cn in (title or "") else "否",
            "英文名": en_title,
            "数据来源": "TXT+DB" if txt else "DB",
            "备注": err,
        })
        print(f"[{brand}] {code} → {title}")
    return pd.DataFrame(out)


# 鞋类品牌里的配件（袜子/帽子/手套/包等）按英文名排除
NON_SHOE_PATTERN = re.compile(
    r"(?i)\b(socks?|beanies?|hats?|caps?|gloves?|mittens?|balaclavas?|scarf|scarves|bags?|backpacks?|"
    r"wallets?|belts?|insoles?|shoelaces?|spray|cream|polish|keyrings?|umbrellas?|accessories|"
    r"coats?|jackets?|parkas?|gilets?|vests?|jumpers?|sweaters?|cardigans?|knitwear|hoodies?|trousers|"
    r"master\s+products)\b"
)
_WOOL_EN_PATTERN = re.compile(
    r"(?i)(\d+\s?%\s*(?:recycled\s+|virgin\s+|merino\s+)?(?:wool|merino|cashmere|sheepskin|shearling|lambswool)"
    r"|merino\s+wool|lambs?['’]?\s?wool|lamb\s+(?:lining|fur|lined)|shearling|sheepskin|cashmere|merino|wool|lamb)"
)


def _wool_snippet(text: str) -> str:
    """优先取带百分比的成分（如 65% Recycled Wool），否则取命中的英文词。"""
    hits = [m.group(0) for m in _WOOL_EN_PATTERN.finditer(text or "")]
    with_pct = [h for h in hits if "%" in h]
    return (with_pct or hits or [""])[0]


def collect_unpublished_wool_shoes(brand: str) -> pd.DataFrame:
    """未发布（无渠道产品ID）且含羊绒类材质的鞋，附预生成标题，按有货尺码数倒序。"""
    brand = brand.lower()
    if brand not in SHOE_BRANDS:
        return pd.DataFrame()
    out = []
    for r in _load_rows(brand, published=False):
        code = r["product_code"]
        en_title = r.get("product_title") or ""
        if not en_title or NON_SHOE_PATTERN.search(en_title):
            continue
        txt = "" if (r.get("product_material") or r.get("feature")) else _read_txt(brand, code)
        blob = " ".join(filter(None, [r.get("product_description"), r.get("product_material"), r.get("feature"), txt]))
        if not detect_wool_keyword(en_title, blob):
            continue
        try:
            title, err = _title_shoe(brand, r, _shoe_content(r, txt)), ""
        except Exception as e:
            title, err = "", str(e)
        out.append({
            "品牌": brand,
            "商品编码": code,
            "英文名": en_title,
            "有货尺码数": int(r.get("sizes_in_stock") or 0),
            "总库存": int(r.get("total_stock") or 0),
            "羊毛成分": _wool_snippet(f"{r.get('feature') or ''} {r.get('product_material') or ''} {blob}"),
            "预生成标题": title,
            "标题字节数": _gbk_len(title),
            "备注": err,
        })
    df = pd.DataFrame(out)
    if not df.empty:
        df = df.sort_values(["有货尺码数", "总库存"], ascending=False).reset_index(drop=True)
    return df


def export_wool_titles(brands: list[str], output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"羊绒商品标题_{datetime.now():%Y%m%d_%H%M}.xlsx"

    frames, summary = {}, []
    for b in brands:
        print(f"\n🟡 {b}: 扫描已发布商品中的羊绒类材质...")
        df = collect_wool_titles(b)
        frames[b] = df
        summary.append({"品牌": b, "商品数": len(df)})
        print(f"✅ {b}: {len(df)} 个")

    unpub = [collect_unpublished_wool_shoes(b) for b in brands if b.lower() in SHOE_BRANDS]
    unpub_df = pd.concat([d for d in unpub if not d.empty], ignore_index=True) if any(not d.empty for d in unpub) else pd.DataFrame()
    for b in brands:
        if b.lower() in SHOE_BRANDS:
            sub = unpub_df[unpub_df["品牌"] == b.lower()] if not unpub_df.empty else unpub_df
            n_stock = int((sub["有货尺码数"] > 0).sum()) if not sub.empty else 0
            for row in summary:
                if row["品牌"] == b:
                    row["未发布羊绒鞋"] = len(sub)
                    row["其中有库存"] = n_stock

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        pd.DataFrame(summary).to_excel(w, sheet_name="汇总", index=False)
        if not unpub_df.empty:
            unpub_df.to_excel(w, sheet_name="未发布羊绒鞋", index=False)
            ws = w.sheets["未发布羊绒鞋"]
            for col, width in zip("ABCDEFGHI", [10, 18, 45, 10, 8, 24, 70, 10, 20]):
                ws.column_dimensions[col].width = width
        for b, df in frames.items():
            df.to_excel(w, sheet_name=b[:31], index=False)
            ws = w.sheets[b[:31]]
            for col, width in zip("ABCDEFGHI", [10, 16, 22, 70, 10, 8, 45, 10, 30]):
                ws.column_dimensions[col].width = width
            for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
                for cell in row:
                    cell.number_format = "@"

    print(f"\n📄 已导出：{out_path}")
    return out_path
