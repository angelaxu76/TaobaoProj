# -*- coding: utf-8 -*-
"""
从一张清单（brand + 货品ID）连库生成备案导入 Excel（Barbour 服装版，无模板）。
- 仅需提供：清单 Excel（两列：brand、货品ID 或 goods_id）
- 其他信息从数据库取
- HSCODE 固定 6201309000
"""

import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

# ======================= ✅【参数配置区】=======================
# 1) 输入清单（两列：brand, 货品ID / goods_id）
INPUT_LIST = Path(r"D:\TB\taofenxiao\barbour_goods_list.xlsx")

# 2) 输出目录 + 工作表名
OUTPUT_DIR = Path(r"D:\TB\taofenxiao\goods")
SHEET_NAME = "sheet"

# 3) 文本兜底（按货号去找TXT的 Product Title，当数据库没标题时）
TEXTS_DIRS = {
    "barbour": r"D:\TB\Products\barbour\publication\TXT",
}

# 4) 品牌映射：从哪个表取哪些字段
BRAND_MAP = {
    "barbour": {
        "table": "barbour_inventory",
        "fields": {
            "channel_item_id": "channel_item_id",
            "product_code": ["product_code", "color_code", "product_name", "code"],
            "size": ["size", "product_size"],
            "title_en": ["product_title", "title_en", "title"],
            "gender": ["gender", "sex"],
            "goods_name": ["goods_name", "product_name_cn"],
            "gtin": ["gtin", "ean", "barcode", "bar_code"],  # EAN/条码
        },
        "name_like_cols": ["goods_name", "product_name"],
        "fallback": {
            "table": "barbour_products",
            "code_cols": ["color_code", "style_name"],
        }
    }
}

# 固定申报要素里的字段
MAIN_COMPONENT = "100%棉"     # 面料成分含量
WEAVE_METHOD  = "机织"        # 织造方法
BRAND_TYPE    = "4"           # 品牌类型
PREF_EXPORT   = "3"           # 出口享惠情况
DECL_KIND     = "大衣"        # 种类（大衣、短大衣、斗篷等）

# Excel列顺序（保持和你现在导出的列一致）
CORRECT_COLUMNS = [
    '*货品ID',
    '*原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）',
    '*规格型号',
    '*主要成分',
    '*品牌',
    '*主要用途',
    '*货品英文名称',
    '*销售单位（枚举值详见:销售单位列表，代码及中文均支持）',
    '*前端宝贝链接',
    '*商品备案价（元）',
    '*HSCODE(枚举值详见:hscode列表)（海关十位编码）',
    '*商品类目',
    '*第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）',
    '*第一数量（请严格对应第一单位要求填写）',
    '*第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）',
    '*第二数量（请严格对应第二单位要求填写）',
    '*申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）'
]

# 固定项（服装）
HSCODE_FIXED = "6201309000"
ORIGIN = "摩尔多瓦"     # 先统一默认值
SPEC = "1件"
BRAND_FIXED = {"barbour": "barbour"}
PURPOSE = "衣着用品"
UOM1 = "件"
QTY1 = 1
UOM2 = "千克"
QTY2 = 1

CATEGORY_MAP = {
    "男": "男装/夹克",
    "男款": "男装/夹克",
    "男士": "男装/夹克",
    "女": "女装/夹克",
    "女款": "女装/夹克",
    "女士": "女装/夹克",
}
CATEGORY_DEFAULT = "男装/夹克"

from config import PGSQL_CONFIG  # 你的数据库连接配置，保持不变

def _pg_url(cfg: dict) -> str:
    host = cfg.get("host") or cfg.get("HOST")
    port = cfg.get("port") or cfg.get("PORT", 5432)
    user = cfg.get("user") or cfg.get("USER")
    pwd  = cfg.get("password") or cfg.get("PASSWORD")
    db   = cfg.get("database") or cfg.get("dbname") or cfg.get("DB") or cfg.get("DATABASE")
    if not all([host, port, user, pwd, db]):
        raise ValueError("PGSQL_CONFIG 缺少 host/port/user/password/dbname")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

ENGINE = create_engine(_pg_url(PGSQL_CONFIG), future=True)

# -------- 工具函数 --------
def first_existing_val(row: dict, candidates: list[str]) -> str | None:
    for c in candidates or []:
        if c in row and row[c] is not None and str(row[c]).strip():
            return str(row[c]).strip()
    return None

def fetch_db_row(brand: str, goods_id: str) -> dict:
    b = BRAND_MAP[brand]
    table = b["table"]
    ch_field = b["fields"]["channel_item_id"]
    sql = text(f"SELECT * FROM {table} WHERE {ch_field} = :cid LIMIT 1")
    with ENGINE.begin() as conn:
        row = conn.execute(sql, {"cid": str(goods_id).strip()}).mappings().first()
    return dict(row) if row else {}

def fetch_fallback_code(brand: str, maybe_keys: dict) -> str | None:
    # 目前没写兜底匹配逻辑（可以以后按 style_name 等做模糊匹配）
    return None

def read_title_from_txt(brand: str, product_code: str) -> str:
    """
    如果数据库里没有英文标题，用 TXT 兜底 Product Title
    TXT 命名假设成 {product_code}.txt
    """
    base = TEXTS_DIRS.get(brand)
    if not base or not product_code:
        return ""
    path = Path(base) / f"{product_code}.txt"
    if not path.exists():
        return ""
    try:
        content = path.read_text("utf-8", errors="ignore")
    except:
        content = path.read_text("gbk", errors="ignore")
    m = re.search(r'Product Title:\s*(.*)', content)
    return m.group(1).strip() if m else ""

def fetch_price(_: str, __: str, ___: str) -> str:
    # 暂时不取备案价，留空
    return ""

def _normalize_gender(val: str | None) -> str:
    if not val:
        return "男"
    s = str(val).strip().lower()
    if any(k in s for k in ["女", "women", "lady", "ladies", "female", "w"]):
        return "女"
    return "男"

def _category_from_gender(g: str) -> str:
    return CATEGORY_MAP.get(g, CATEGORY_DEFAULT)

def _gender_label_for_decl(g: str) -> tuple[str, str]:
    """
    返回 (括号里的类别词, 实际值)，例如 ('男式','男式') 或 ('女式','女式')
    """
    if g == "女":
        return ("女式", "女式")
    return ("男式", "男式")

def build_row(brand: str, goods_id: str) -> dict:
    b = BRAND_MAP[brand]
    fields = b["fields"]

    db = fetch_db_row(brand, goods_id)

    # 货号（code）
    code = first_existing_val(db, fields.get("product_code"))
    if not code:
        code = fetch_fallback_code(brand, db)

    # 性别/类目
    gender_raw = first_existing_val(db, fields.get("gender"))
    gender_norm = _normalize_gender(gender_raw)
    category = _category_from_gender(gender_norm)
    bracket_label, bracket_value = _gender_label_for_decl(gender_norm)

    # 英文标题
    title_en = first_existing_val(db, fields.get("title_en"))
    if not title_en and code:
        title_en = read_title_from_txt(brand, code)

    # GTIN/EAN
    gtin = first_existing_val(db, fields.get("gtin")) or ""

    # 备案价
    price = fetch_price(brand, code or "", "")

    # 填充物（暂无则空）
    filling = ""

    # 先拼一个申报要素字符串
    declaration = (
        f"类别（{bracket_label}）:{bracket_value}|"
        f"货号:{code or ''}|"
        f"出口享惠情况:{PREF_EXPORT}|"
        f"种类（大衣、短大衣、斗篷等）:{DECL_KIND}|"
        f"GTIN:{gtin}|"
        f"面料成分含量:{MAIN_COMPONENT}|"
        f"织造方法（机织等）:{WEAVE_METHOD}|"
        f"品牌类型:{BRAND_TYPE}|"
        f"如有填充物，请注明成分含量:{filling}|"
        f"品牌（中文或外文名称）:BARBOUR"
    )

    # 如果没拿到货号，打一个提醒进去（但不要让整行报错）
    if not code:
        declaration = declaration + "|⚠缺少货号"

    row = {
        '*货品ID': goods_id,
        '*原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）': ORIGIN,
        '*规格型号': SPEC,
        '*主要成分': MAIN_COMPONENT,
        '*品牌': BRAND_FIXED.get(brand, brand),
        '*主要用途': PURPOSE,
        '*货品英文名称': title_en or "",
        '*销售单位（枚举值详见:销售单位列表，代码及中文均支持）': UOM1,
        '*前端宝贝链接': '',
        '*商品备案价（元）': price,
        '*HSCODE(枚举值详见:hscode列表)（海关十位编码）': HSCODE_FIXED,
        '*商品类目': category,
        '*第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）': UOM1,
        '*第一数量（请严格对应第一单位要求填写）': QTY1,
        '*第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）': UOM2,
        '*第二数量（请严格对应第二单位要求填写）': QTY2,
        '*申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）': declaration
    }

    return row

def main(
    input_list: Path = INPUT_LIST,
    output_dir: Path = OUTPUT_DIR,
    sheet_name: str = SHEET_NAME
):
    df = pd.read_excel(input_list, dtype=str)

    # 校验列
    if "brand" not in df.columns:
        raise KeyError("输入清单必须包含列：brand")

    if "货品ID" in df.columns:
        gid_col = "货品ID"
    elif "goods_id" in df.columns:
        gid_col = "goods_id"
    else:
        raise KeyError("输入清单必须包含列：货品ID（或 goods_id）")

    # 仅支持 barbour
    df["brand"] = df["brand"].str.lower().str.strip()

    rows = []
    for i, r in df.iterrows():
        brand = r["brand"]
        goods_id = str(r[gid_col]).strip()

        if brand != "barbour":
            print(f"⚠ 跳过第{i+1}行：仅支持 brand=barbour，收到 {brand}")
            continue

        if not goods_id:
            print(f"⚠ 跳过第{i+1}行：空 货品ID")
            continue

        try:
            rows.append(build_row(brand, goods_id))
        except Exception as e:
            print(f"❌ 第{i+1}行失败（brand={brand}, 货品ID={goods_id}）：{e}")

    out_df = pd.DataFrame(rows, columns=CORRECT_COLUMNS)

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"备案导入_{ts}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        out_df.to_excel(w, sheet_name=sheet_name, index=False)

    print(f"✅ 生成完成：{out_path}")

if __name__ == "__main__":
    main()
