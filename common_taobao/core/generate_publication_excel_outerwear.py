# -*- coding: utf-8 -*-
"""
专用：服装外套（REISS / Barbour）
从数据库筛选外套 → 读取 TXT → 生成淘宝标题 → 计算价格 → 导出 Excel

用法示例：
    from generate_publication_excel_outerwear import generate_publication_excels_clothing
    generate_publication_excels_clothing(
        brand="reiss",
        pricing_mode="jingya",   # "jingya" | "taobao"
        min_sizes=3,
        min_total_stock=9
    )
"""

import os
import re
import shutil
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy import text 

# === 项目配置 ===
from config import BRAND_CONFIG, SETTINGS
from common_taobao.core.generate_taobao_title_outerwear import generate_taobao_title as gen_title_outerwear

# === 价格工具：优先用项目内路径，回退到本地 price_utils.py ===
try:
    from common_taobao.core.price_utils import (
        calculate_jingya_prices,
        calculate_discount_price_from_float,
    )
except Exception:
    # 兼容你上传的独立文件
    from price_utils import (
        calculate_jingya_prices,
        calculate_discount_price_from_float,
    )

# === 标题：优先用“外套专用”脚本，失败回退通用脚本 ===
from importlib import import_module

def _load_title_func(candidates):
    for mod in candidates:
        try:
            m = import_module(mod)
            func = getattr(m, "generate_taobao_title", None)
            if callable(func):
                print(f"🧩 使用标题模块：{mod}")
                return func
        except Exception as _:
            pass
    return None

# 优先：外套专用脚本（请把 generate_taobao_title_outerwear.py 放到其中一个路径）
gen_title_outerwear = _load_title_func([
    "common_taobao.core.generate_taobao_title_outerwear",
    "common_taobao.generate_taobao_title_outerwear",
    "generate_taobao_title_outerwear",
])

# 回退：通用（你现有的鞋类脚本）
gen_title_general = _load_title_func([
    "common_taobao.core.generate_taobao_title",
    "common_taobao.generate_taobao_title",
    "generate_taobao_title",
])

if gen_title_general is None:
    raise ImportError("找不到通用标题脚本 generate_taobao_title（请确认模块路径）")



# ==== 服装固定字段（默认） ====
上市年份季节 = "2025年秋季"
版型 = "标准"
面料 = "涤纶"
衣门襟 = "拉链"
厚薄 = "常规"
领口设计 = "翻领"

地区国家 = "英国"
发货时间 = "7"
运费模版 = "parcelforce"
第一计量单位 = "1"
第二计量单位 = "1"
销售单位 = "件"
品名 = "外套"
海关款式 = "外衣"

# ===== 工具函数 =====
def extract_field(name: str, content: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*[:：]\s*(.+)", content, flags=re.I)
    return m.group(1).strip() if m else ""

def determine_outerwear_type(title_en: str, content: str, style_cat: str) -> str:
    """将英文线索映射到中文外套类型（仅用于导出‘类目’列；不影响 DB）"""
    t = (title_en or "").lower()
    c = (content or "").lower()
    s = (style_cat or "").lower()
    blob = " ".join([t, c, s])
    if re.search(r"\btrench|mac|raincoat\b", blob): return "风衣"
    if re.search(r"\b(parka)\b", blob): return "派克"
    if re.search(r"\b(bomber)\b", blob): return "飞行员夹克"
    if re.search(r"\b(blazer|tailor(?:ed)?\s+jacket)\b", blob): return "西装外套"
    if re.search(r"\b(gilet|waistcoat)\b", blob): return "马甲"
    if re.search(r"\b(puffer|down|quilt(?:ed)?|padded)\b", blob): return "羽绒/绗缝"
    if re.search(r"\b(suede).*jacket|jacket.*\bsuede\b", blob): return "麂皮夹克"
    if re.search(r"\b(biker|moto|aviator|shearling).*jacket|jacket.*\bleather\b|\bleather\b.*jacket", blob): return "皮夹克"
    if re.search(r"\bovercoat\b", blob): return "大衣"
    if re.search(r"\bcoat\b", blob): return "大衣"
    if re.search(r"\bjacket\b", blob): return "夹克"
    return "外套"

def _title_for_outerwear(product_code: str, content: str, brand_key: str) -> str:
    """只用外套标题脚本，返回字符串"""
    r = gen_title_outerwear(product_code, content, brand_key)
    # 兼容返回 dict 或 str
    if isinstance(r, dict):
        return r.get("taobao_title") or r.get("title_cn") or ""
    return str(r or "")


def _calc_price(base_price_gbp: float, mode: str) -> float:
    """
    mode="jingya" → calculate_jingya_prices() 的 retail
    mode="taobao" → calculate_discount_price_from_float()
    """
    base_price = float(base_price_gbp or 0)
    if base_price <= 0:
        return 0
    mode = (mode or "jingya").lower()
    if mode == "taobao":
        return float(calculate_discount_price_from_float(base_price) or 0)
    # jingya：取 retail（第二个返回值），汇率优先 SETTINGS
    try:
        exch = SETTINGS.get("EXCHANGE_RATE", 9.7)
    except Exception:
        exch = 9.7
    untaxed, retail = calculate_jingya_prices(base_price, delivery_cost=7, exchange_rate=exch)
    return float(retail or 0)



...
def _safe_path_part(s: str) -> str:
    # 替换 Windows 禁字符：\ / : * ? " < > | 以及首尾空格
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(s).strip()) or "未分类"


def generate_publication_excels_clothing(
    brand: str,
    pricing_mode: str = "jingya",
    min_sizes: int = 3,
    min_total_stock: int = 9,
    gender_filter: str | None = None,           # 新增
    category_filter: list[str] | None = None    # 新增（style_category 原词）
):
    """
    生成服装外套发布用 Excel（分性别/类目导出多份）
    - brand: "reiss" / "barbour" ...
    - pricing_mode: "jingya" | "taobao"
    - min_sizes: 最少有货尺码个数（基于 DB 的 stock_count>1 统计）
    - min_total_stock: 最少总库存
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    cfg = BRAND_CONFIG[brand]
    txt_folder = Path(cfg["TXT_DIR"])
    output_base = Path(cfg["OUTPUT_DIR"]) / "publication_excels_outerwear"
    image_src_dir = Path(cfg.get("IMAGE_DIR", txt_folder.parent))  # 如果没配 IMAGE_DIR，就近用
    image_dst_dir = output_base / "images"
    pg = cfg["PGSQL_CONFIG"]

    # ==== 连接数据库 ====
    print(f"\n🔌 连接数据库：{brand.upper()}")
    engine = create_engine(
        f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['dbname']}"
    )

    # ==== 只筛“外套” ====
    print("\n📊 查询外套候选商品...")
    table = cfg["TABLE_NAME"]
    gf_sql = ""
    if gender_filter:
        gf = gender_filter.strip().lower()
        gf_sql = f" AND lower(ci.gender) LIKE '{'women' if gf.startswith('w') else 'men'}%' "

    cf_sql = ""
    if category_filter:
        # 统一为小写，并只允许字母/空格，避免非法字符
        cats = [re.sub(r"[^a-z ]+", "", c.strip().lower()) for c in category_filter if c.strip()]
        if cats:
            in_list = ", ".join("'" + c + "'" for c in cats)
            cf_sql = f" AND lower(ci.style_category) IN ({in_list}) "

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
    JOIN size_counts sc ON ci.product_code = sc.product_code
    JOIN publish_status ps ON ci.product_code = ps.product_code
    WHERE ps.any_published = FALSE
      AND sc.available_sizes >= {int(min_sizes)}
      AND sc.total_stock > {int(min_total_stock)}
      -- 外套大类（兜底匹配），如指定 category_filter 则进一步收窄
      AND (
            lower(ci.style_category) ~ '(coat|jacket|blazer|waistcoat|gilet|parka|puffer|quilt)'
         OR lower(ci.product_title || ' ' || ci.product_description) ~
            '(trench|mac|raincoat|coat|jacket|blazer|waistcoat|gilet|parka|puffer|down|quilt(ed)?|padded)'
      )
      {gf_sql}
      {cf_sql}
    GROUP BY ci.product_code
    """
    with engine.connect() as conn:
        df = pd.read_sql_query(sql=text(query), con=conn)
    print(f"✅ 候选商品数：{len(df)}")
    if df.empty:
        print("⚠️ 没有符合条件的外套，任务结束")
        return

    # ==== 读取 TXT + 标题 + 价格 ====
    rows = []
    print("\n📦 读取 TXT 并生成行数据...")
    for _, r in df.iterrows():
        code = str(r["product_code"]).strip().upper()
        txt_path = txt_folder / f"{code}.txt"
        if not txt_path.exists():
            print(f"❌ 缺 TXT：{txt_path}")
            continue

        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 标题
        title_en = extract_field("Product Name", content) or (r.get("product_title") or "")
        title_cn = _title_for_outerwear(code, content, brand)

        # 价格（GBP → RMB）
        base_price = float(r["discount_price_gbp"] or 0) or float(r["original_price_gbp"] or 0) or 0
        rmb_price = _calc_price(base_price, pricing_mode)

        # 性别 + 类目（中文）
        gender_raw = str(r.get("gender") or "")
        gender_cn = "女装" if gender_raw.lower().startswith("w") else ("男装" if gender_raw.lower().startswith("m") else "未知")
        style_cat = str(r.get("style_category") or "")
        cat_cn = determine_outerwear_type(title_en, content, style_cat)

        row = {
            "英文标题": title_en,
            "标题": title_cn,
            "商品编码": code,
            "价格": rmb_price,
            # === 服装属性（默认值） ===
            "上市年份季节": 上市年份季节,
            "版型": 版型,
            "面料": 面料,
            "衣门襟": 衣门襟,
            "厚薄": 厚薄,
            "领口设计": 领口设计,
            # === 其他通用列 ===
            "地区国家": 地区国家,
            "发货时间": 发货时间,
            "运费模版": 运费模版,
            "品牌": brand,
            "性别": gender_cn,
            "类目": cat_cn,
            "商品链接": r.get("product_url") or extract_field("Source URL", content),
        }
        rows.append(row)

    df_all = pd.DataFrame(rows)
    if df_all.empty:
        print("⚠️ 没有可生成的数据")
        return

    # ==== 导出 Excel（分性别/类目） ====
    output_base.mkdir(parents=True, exist_ok=True)
    print("\n📤 导出 Excel ...")
    for (gender, category), sub in df_all.groupby(["性别", "类目"], dropna=False):
        g = _safe_path_part(gender or "")
        c = _safe_path_part(category or "")
        out_file = output_base / f"{brand}_{g}_{c}.xlsx"
        if out_file.exists():
            out_file.unlink()
        sub.drop(columns=["性别", "类目"]).to_excel(out_file, index=False)
        print(f"✅ 导出：{out_file}")


    # ==== 可选：拷贝图片（若需要，与鞋类脚本保持一致风格） ====
    try:
        image_dst_dir.mkdir(parents=True, exist_ok=True)
        print("\n🖼️ 复制图片 ...")
        missing_codes = []
        for code in df_all["商品编码"].unique():
            matched = list(image_src_dir.glob(f"{code}*.jpg"))
            if not matched:
                missing_codes.append(code)
                continue
            for img in matched:
                shutil.copy(img, image_dst_dir / img.name)
        # 输出清单
        pub_codes_file = cfg["OUTPUT_DIR"] / "publication_codes_outerwear.txt"
        miss_codes_file = cfg["OUTPUT_DIR"] / "missing_codes_outerwear.txt"
        with open(pub_codes_file, "w", encoding="utf-8") as f:
            for code in sorted(set(df_all["商品编码"].tolist())):
                f.write(f"{code}\n")
        with open(miss_codes_file, "w", encoding="utf-8") as f:
            for code in sorted(set(missing_codes)):
                f.write(f"{code}\n")
        print(f"📝 已写出：{pub_codes_file} / {miss_codes_file}")
    except Exception as _:
        pass

    print("\n✅ 完成。")
