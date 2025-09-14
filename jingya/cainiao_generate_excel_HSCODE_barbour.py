# -*- coding: utf-8 -*-
"""
从一张清单（brand + 货品ID）连库生成备案导入 Excel（Barbour 服装版，无模板）。
- 仅需提供：清单 Excel（两列：brand、货品ID 或 goods_id）
- 其他信息从数据库取：英文标题尽量从库字段获取，缺失可按需扩展 TXT 兜底
- HSCODE 固定 6201309000
- 第一单位/数量：件 / 1
- 第二单位/数量：千克 / 1
- 主要成分：100%棉
- 申报要素按你的要求拼装（见 build_row）
- 输出字段顺序与旧脚本一致；工作表名可配置

依赖：pandas, openpyxl, SQLAlchemy(psycopg2)
数据库：读取 config.PGSQL_CONFIG（支持 host/port/user/password/dbname）
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

# 3) 文本兜底（Barbour一般不需要，可留空或后续扩展）
TEXTS_DIRS = {
    "barbour": r"D:\TB\Products\barbour\publication\TXT",
}

# 4) 品牌表与字段映射（按你的数据库实际情况调整）
# 说明：
# - 首选从 barbour_inventory 通过 channel_item_id 定位行，取 product_code/color_code 作为“货号”
# - 若找不到，再尝试根据可能的关联信息去 barbour_products 兜底 color_code
# 1) 在 BRAND_MAP["barbour"]["fields"] 里补上 GTIN/EAN/条码候选
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
            # ➕ 新增条码候选（脚本会自动取第一个有值的）
            "gtin": ["gtin", "ean", "barcode", "bar_code"]
        },
        "name_like_cols": ["goods_name", "product_name"],
        "fallback": {
            "table": "barbour_products",
            "code_cols": ["color_code", "style_name"],
        }
    }
}

# 2) 如果你之前把 MAIN_COMPONENT 设为 100%棉，这里沿用即可
MAIN_COMPONENT = "100%棉"     # 用于“面料成分含量”
WEAVE_METHOD  = "机织"        # 织造方法（机织等）固定为“机织”
BRAND_TYPE    = "4"           # 品牌类型固定为 4
PREF_EXPORT   = "3"           # 出口享惠情况固定为 3
DECL_KIND     = "大衣"        # 种类（大衣、短大衣、斗篷等）按你的示例固定为“大衣”

# 5) 备案字段顺序（保持与旧脚本一致）
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

# 6) 固定项（服装版）
HSCODE_FIXED = "6201309000"
ORIGIN = "摩尔多瓦"             # 如需精确可对接 offers/产地字段；先给默认
SPEC = "1件"               # 规格型号
BRAND_FIXED = {"barbour": "barbour"}
PURPOSE = "衣着用品"
UOM1 = "件";  QTY1 = 1
UOM2 = "千克"; QTY2 = 1

# 类目：随性别动态映射（兜底男装/夹克）
CATEGORY_MAP = {
    "男": "男装/夹克",
    "男款": "男装/夹克",
    "男士": "男装/夹克",
    "女": "女装/夹克",
    "女款": "女装/夹克",
    "女士": "女装/夹克",
}
CATEGORY_DEFAULT = "男装/夹克"

MAIN_COMPONENT = "100%棉"  # 主要成分（字段“主要成分”）

# ======================= 连接数据库 =======================
from config import PGSQL_CONFIG  # 兼容 host/port/user/password/dbname

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

# ======================= 工具函数 =======================
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
    """
    当主表找不到 product_code/color_code 时，去 barbour_products 兜底 color_code。
    这里可根据你数据库能关联的键进行扩展（如通过英文标题、匹配关键词等）。
    """
    fb = BRAND_MAP[brand].get("fallback")
    if not fb: return None
    table = fb["table"]
    code_cols = fb["code_cols"] or ["color_code"]

    # 示例：若主表含 style_name 或 color/size 等可用于关联，请在这里写关联逻辑。
    # 这里给一个“保守空实现”，返回 None；你可按需要补充。
    return None

def read_title_from_txt(brand: str, product_code: str) -> str:
    base = TEXTS_DIRS.get(brand)
    if not base: return ""
    path = Path(base) / f"{product_code}.txt"
    if not path.exists(): return ""
    try:
        content = path.read_text("utf-8", errors="ignore")
    except:
        content = path.read_text("gbk", errors="ignore")
    m = re.search(r'Product Title:\s*(.*)', content)
    return m.group(1).strip() if m else ""

def fetch_price(_: str, __: str, ___: str) -> str:
    # 如需对接定价/备案价，这里接到你的价格表，否则留空即可
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
    """返回 (括号里的类别词, 实际值)，如 ('男式', '男式') 或 ('女式', '女式')"""
    if g == "女":
        return ("女式", "女式")
    return ("男式", "男式")

def build_row(brand: str, goods_id: str) -> dict:
    b = BRAND_MAP[brand]
    fields = b["fields"]

    db = fetch_db_row(brand, goods_id)

    # 货号
    code = first_existing_val(db, fields.get("product_code"))
    if not code:
        code = fetch_fallback_code(brand, db)

    # 性别与类目
    gender_raw = first_existing_val(db, fields.get("gender"))
    gender_norm = _normalize_gender(gender_raw)
    category = _category_from_gender(gender_norm)
    bracket_label, bracket_value = _gender_label_for_decl(gender_norm)  # ('男式','男式') / ('女式','女式')

    # 英文标题
    title_en = first_existing_val(db, fields.get("title_en")) or (read_title_from_txt(brand, code) if code else "")

    # GTIN/EAN
    gtin = first_existing_val(db, fields.get("gtin")) or ""

    # 备案价（如需）
    price = fetch_price(brand, code or "", "")

    # 如有填充物（可从库扩展一个字段，比如 filling / padding_content）
    filling = ""  # 没数据就留空

    # —— 按你给的“成功备案导出格式”拼接 —— #
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
    if not code:
        row['申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）'] += "|⚠缺少货号"
    return row

def main(
    input_list: Path = INPUT_LIST,
    output_dir: Path = OUTPUT_DIR,
    sheet_name: str = SHEET_NAME
):
    df = pd.read_excel(input_list, dtype=str)
    # 兼容列名
    if "brand" not in df.columns:
        raise KeyError("输入清单必须包含列：brand")
    gid_col = "货品ID" if "货品ID" in df.columns else ("goods_id" if "goods_id" in df.columns else None)
    if gid_col is None:
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

    # 直接输出干净 Excel
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        out_df.to_excel(w, sheet_name=sheet_name, index=False)

    print(f"✅ 生成完成：{out_path}")

if __name__ == "__main__":
    main()
