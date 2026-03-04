# -*- coding: utf-8 -*-
"""
服装专用（REISS / Barbour）
从数据库筛选 → 读取 TXT → 生成淘宝标题 → 计算价格 → 导出 Excel

保持管道兼容：
- 函数名/参数不变：generate_publication_excels_clothing(...)
- 未传 category_filter → 仍按“外套家族”筛选
- 传入 category_filter（如 ["Dresses"]）→ 启用通用服装筛选（不强制外套关键字），并做正则归一化匹配
- 只考虑服装；已删除鞋类兜底
"""

import re, os, shutil, pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from importlib import import_module
from config import BRAND_CONFIG, SETTINGS

# ---------- 动态加载标题模块（仅服装） ----------
def _load_title_func(candidates):
    for mod in candidates:
        try:
            m = import_module(mod)
            fn = getattr(m, "generate_taobao_title", None)
            if callable(fn):
                print(f"🧩 使用标题模块：{mod}")
                return fn
        except Exception:
            pass
    return None

# 外套专用（存在则用；不存在回退到服装通用）
gen_title_outerwear = _load_title_func([
    "common.text.generate_taobao_title_outerwear",
    "generate_taobao_title_outerwear",
])

# 服装通用（裙/衬衫/针织/裤/T恤/连体裤…）
gen_title_apparel = _load_title_func([
    "common.text.generate_taobao_title_apparel",
    "generate_taobao_title_apparel",
])
if gen_title_apparel is None:
    raise ImportError("找不到服装通用标题脚本 generate_taobao_title_apparel")

# ---------- 价格工具 ----------
try:
    from common.pricing.price_utils import (
        calculate_jingya_prices,
        calculate_discount_price_from_float,
    )
except Exception:
    from price_utils import (
        calculate_jingya_prices,
        calculate_discount_price_from_float,
    )

# ---------- 服装默认属性 ----------
上市年份季节 = "2025年秋季"
版型, 面料, 衣门襟, 厚薄, 领口设计 = "标准", "涤纶", "拉链", "常规", "翻领"
地区国家, 发货时间, 运费模版 = "英国", "7", "parcelforce"
第一计量单位 = 第二计量单位 = "1"
销售单位 = "件"

# ---------- 工具 ----------
def extract_field(name: str, content: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*[:：]\s*(.+)", content or "", flags=re.I)
    return m.group(1).strip() if m else ""

def _safe_path_part(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(s).strip()) or "未分类"

# 类目中文映射（服装）
def determine_category_cn(style_cat: str, title_en: str, content: str) -> str:
    s = (style_cat or "").strip().lower()
    mapping = {
        "dresses":"连衣裙","dress":"连衣裙",
        "skirts":"半身裙","skirt":"半身裙",
        "shirts":"衬衫","blouses":"衬衫","shirt":"衬衫","blouse":"衬衫",
        "trousers":"长裤","pants":"长裤","jeans":"长裤",
        "knitwear":"针织衫","jumpers":"针织衫","sweaters":"针织衫","cardigans":"针织衫",
        "tops":"上衣","t shirts":"上衣","tees":"上衣",
        "shorts":"短裤",
        "jumpsuits":"连体裤","playsuits":"连体裤",
        "coats":"外套","jackets":"外套","blazers":"外套","waistcoats":"外套",
        "gilets":"外套","parkas":"外套","puffer":"外套",
        "sweatshirts":"卫衣","sweatshirt":"卫衣","hoodies":"卫衣","hoodie":"卫衣","fleece":"卫衣",
        "lingerie":"内衣","underwear":"内衣","bras":"内衣",
        "jumpsuits":"连体裤",
        "other":"服装",
    }
    if s in mapping: return mapping[s]
    t = (title_en or "").lower(); c = (content or "").lower(); blob = f"{t} {c}"
    if re.search(r"\b(dress|dresses)\b", blob): return "连衣裙"
    if re.search(r"\b(skirt|skirts)\b", blob):  return "半身裙"
    if re.search(r"\b(coat|jacket|blazer|waistcoat|gilet|parka|puffer|quilt)\b", blob): return "外套"
    if re.search(r"\b(trouser|pant|jean)\b", blob): return "长裤"
    if re.search(r"\b(shirt|blouse)\b", blob): return "衬衫"
    if re.search(r"\b(jumper|sweater|cardigan|knit)\b", blob): return "针织衫"
    if re.search(r"\b(t-?shirt|top|tee)\b", blob): return "上衣"
    return "服装"

def _name_and_customs_by_cat(cat_cn: str) -> tuple[str, str]:
    if cat_cn == "连衣裙": return "连衣裙","裙装"
    if cat_cn == "半身裙": return "半身裙","裙装"
    if cat_cn in {"衬衫","上衣","针织衫"}: return cat_cn,"上衣"
    if cat_cn in {"长裤","短裤"}: return cat_cn,"下装"
    if cat_cn == "连体裤": return "连体裤","下装"
    return ("外套" if cat_cn=="外套" else "服装",
            "外衣" if cat_cn=="外套" else "服装")

def _title_outerwear(code: str, content: str, brand_key: str, fallback_en: str) -> str:
    if gen_title_outerwear:
        r = gen_title_outerwear(code, content, brand_key)
        return r.get("taobao_title") if isinstance(r, dict) else str(r or fallback_en)
    # 无外套专用脚本 → 服装通用
    r = gen_title_apparel(code, content, brand_key)
    return r.get("taobao_title") if isinstance(r, dict) else str(r or fallback_en)

def _title_apparel(code: str, content: str, brand_key: str, fallback_en: str) -> str:
    r = gen_title_apparel(code, content, brand_key)
    return r.get("taobao_title") if isinstance(r, dict) else str(r or fallback_en)

def _calc_price(base_price_gbp: float, mode: str) -> float:
    base = float(base_price_gbp or 0)
    if base <= 0: return 0.0
    if (mode or "jingya").lower() == "taobao":
        return float(calculate_discount_price_from_float(base) or 0)
    exch = SETTINGS.get("EXCHANGE_RATE", 9.7) if isinstance(SETTINGS, dict) else 9.7
    _, retail = calculate_jingya_prices(base, delivery_cost=7, exchange_rate=exch)
    return float(retail or 0)

# ================= 主函数（签名保持不变） =================
def generate_publication_excels_clothing(
    brand: str,
    pricing_mode: str = "jingya",
    min_sizes: int = 3,
    min_total_stock: int = 9,
    gender_filter: str | None = None,
    category_filter: list[str] | None = None
):
    brand = (brand or "").lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    cfg = BRAND_CONFIG[brand]
    txt_folder = Path(cfg["TXT_DIR"])
    output_base = Path(cfg["OUTPUT_DIR"]) / "publication_excels_outerwear"  # 维持原目录以兼容
    image_src_dir = Path(cfg.get("IMAGE_DIR", txt_folder.parent))
    image_dst_dir = output_base / "images"
    pg = cfg["PGSQL_CONFIG"]

    print(f"\n🔌 连接数据库：{brand.upper()}")
    engine = create_engine(f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['dbname']}")

    # 过滤：是否仅外套
    outerwear_only = not (category_filter and any(c.strip() for c in category_filter))

    gf_sql = ""
    if gender_filter:
        gf = gender_filter.strip().lower()
        gf_sql = f" AND lower(ci.gender) LIKE '{'women' if gf.startswith('w') else 'men'}%' "

    cf_sql = ""
    if category_filter:
        cats = [re.sub(r"[^a-z ]+", "", c.strip().lower()) for c in category_filter if c.strip()]
        cats = [c for c in cats if c]
        if cats:
            in_list = ", ".join("'" + c + "'" for c in cats)
            cf_sql = (
                f" AND regexp_replace(lower(ci.style_category), '[^a-z ]+', '', 'g') "
                f"IN ({in_list}) "
            )

    print(f"\n📊 查询{'外套候选商品' if outerwear_only else '候选商品'}...")
    table = cfg["TABLE_NAME"]

    outerwear_where = ""
    if outerwear_only:
        outerwear_where = """
          AND (
                lower(ci.style_category) ~ '(coat|jacket|blazer|waistcoat|gilet|parka|puffer|quilt)'
             OR lower(ci.product_title || ' ' || ci.product_description) ~
                '(trench|mac|raincoat|coat|jacket|blazer|waistcoat|gilet|parka|puffer|down|quilt(ed)?|padded)'
          )
        """

    query = f"""
    WITH size_counts AS (
        SELECT product_code,
               COUNT(*) FILTER (WHERE stock_count > 1) AS available_sizes,
               SUM(stock_count)                        AS total_stock
        FROM {table}
        GROUP BY product_code
    ),
    publish_status AS (
        SELECT product_code, BOOL_OR(is_published) AS any_published
        FROM {table}
        GROUP BY product_code
    )
    SELECT DISTINCT ci.product_code,
           MIN(ci.original_price_gbp) AS original_price_gbp,
           MIN(ci.discount_price_gbp) AS discount_price_gbp,
           MIN(ci.gender)             AS gender,
           MIN(ci.product_url)        AS product_url,
           MIN(ci.product_title)      AS product_title,
           MIN(ci.product_description)AS product_description,
           MIN(ci.style_category)     AS style_category
    FROM {table} ci
    JOIN size_counts   sc ON ci.product_code = sc.product_code
    JOIN publish_status ps ON ci.product_code = ps.product_code
    WHERE ps.any_published = FALSE
      AND sc.available_sizes >= {int(min_sizes)}
      AND sc.total_stock > {int(min_total_stock)}
      {outerwear_where}
      {gf_sql}
      {cf_sql}
    GROUP BY ci.product_code
    """
    with engine.connect() as conn:
        df = pd.read_sql_query(sql=text(query), con=conn)
    print(f"✅ 候选商品数：{len(df)}")
    if df.empty:
        print("⚠️ 没有符合条件的商品，任务结束"); return

    # 读取 TXT + 标题 + 价格
    rows = []
    print("\n📦 读取 TXT 并生成行数据...")
    for _, r in df.iterrows():
        code = str(r["product_code"]).strip().upper()
        txt_path = txt_folder / f"{code}.txt"
        if not txt_path.exists():
            print(f"❌ 缺 TXT：{txt_path}"); continue

        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()

        title_en = extract_field("Product Name", content) or (r.get("product_title") or "")
        cat_cn = determine_category_cn(r.get("style_category"), title_en, content)

        # 标题：外套→外套专用（若无则用服装通用）；其它一律服装通用
        if cat_cn == "外套":
            title_cn = _title_outerwear(code, content, brand, title_en)
        else:
            title_cn = _title_apparel(code, content, brand, title_en)

        base_price = float(r["discount_price_gbp"] or 0) or float(r["original_price_gbp"] or 0) or 0
        rmb_price = _calc_price(base_price, pricing_mode)

        gender_raw = str(r.get("gender") or "")
        gender_cn = "女装" if gender_raw.lower().startswith("w") else ("男装" if gender_raw.lower().startswith("m") else "未知")

        品名_local, 海关款式_local = _name_and_customs_by_cat(cat_cn)

        rows.append({
            "英文标题": title_en,
            "标题": title_cn,
            "商品编码": code,
            "价格": rmb_price,
            "上市年份季节": 上市年份季节,
            "版型": 版型, "面料": 面料, "衣门襟": 衣门襟, "厚薄": 厚薄, "领口设计": 领口设计,
            "地区国家": 地区国家, "发货时间": 发货时间, "运费模版": 运费模版,
            "品牌": brand, "性别": gender_cn, "类目": cat_cn,
            "品名": 品名_local, "海关款式": 海关款式_local,
            "商品链接": r.get("product_url") or extract_field("Source URL", content),
        })

    df_all = pd.DataFrame(rows)
    if df_all.empty:
        print("⚠️ 没有可生成的数据"); return

    # 导出 Excel（分性别/类目）
    output_base.mkdir(parents=True, exist_ok=True)
    print("\n📤 导出 Excel ...")
    for (gender, category), sub in df_all.groupby(["性别", "类目"], dropna=False):
        g = _safe_path_part(gender or ""); c = _safe_path_part(category or "")
        out_file = output_base / f"{brand}_{g}_{c}.xlsx"
        if out_file.exists(): out_file.unlink()
        sub.drop(columns=["性别","类目"]).to_excel(out_file, index=False)
        print(f"✅ 导出：{out_file}")

    # 复制图片 + 清单（保持兼容）
    try:
        image_dst_dir.mkdir(parents=True, exist_ok=True)
        print("\n🖼️ 复制图片 ...")
        missing = []
        for code in df_all["商品编码"].unique():
            matched = list(image_src_dir.glob(f"{code}*.jpg"))
            if not matched: missing.append(code); continue
            for img in matched: shutil.copy(img, image_dst_dir / img.name)
        pub_codes_file = cfg["OUTPUT_DIR"] / "publication_codes_outerwear.txt"
        miss_codes_file = cfg["OUTPUT_DIR"] / "missing_codes_outerwear.txt"
        with open(pub_codes_file,"w",encoding="utf-8") as f:
            for code in sorted(set(df_all["商品编码"])): f.write(f"{code}\n")
        with open(miss_codes_file,"w",encoding="utf-8") as f:
            for code in sorted(set(missing)): f.write(f"{code}\n")
        print(f"📝 已写出：{pub_codes_file} / {miss_codes_file}")
    except Exception:
        pass

    print("\n✅ 完成。")
