# -*- coding: utf-8 -*-
"""
从一张清单（brand + 货品ID）连库生成备案导入 Excel（无模板版）。
- 仅需提供：清单 Excel（两列：brand、货品ID）
- 其他信息从数据库取，英文标题取不到时尝试 TXT 兜底
- HSCODE 固定 6405200090
- 输出字段顺序与以往一致；工作表名可配置

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
# 1) 仅需这一个输入（两列：brand, 货品ID）
INPUT_LIST = Path(r"D:\TB\taofenxiao\goods_list.xlsx")

# 2) 输出目录 + 工作表名（将与“之前代码”一致的名字填在这里）
OUTPUT_DIR = Path(r"D:\TB\taofenxiao\goods")
SHEET_NAME = "sheet"   # ← 如果你之前的工作表名不一样，请改成之前的名字

# 3) 品牌 TXT 路径（英文标题兜底；可留空）
TEXTS_DIRS = {
    "camper": r"D:\TB\Products\camper\publication\TXT",
    "geox": r"D:\TB\Products\geox\publication\TXT",
    "clarks": r"D:\TB\Products\clarks_jingya\publication\TXT",
    "ecco":   r"D:\TB\Products\ecco\publication\TXT",
}

# 4) 数据库表与字段映射（按你的现状；字段候选名会自动择优）
#    ⭐ 新增 gender 映射，优先从库里读取性别
BRAND_MAP = {
    "camper": {
        "table": "camper_inventory",
        "fields": {
            "channel_item_id": "channel_item_id",
            "product_code": ["product_code", "product_name", "code"],   # 编码优先次序
            "size": ["size", "product_size"],
            "title_en": ["product_title", "title_en", "title"],
            "goods_name": ["goods_name", "product_name_cn", "name_cn"], # 用于兜底解析
            "gender": ["gender", "sex"],                                # ← 新增
        },
        "name_like_cols": ["goods_name", "product_name"],
    },
    "clarks": {
        "table": "clarks_jingya_inventory",
        "fields": {
            "channel_item_id": "channel_item_id",
            "product_code": ["product_code", "product_name", "code"],
            "size": ["size", "product_size"],
            "title_en": ["product_title", "title_en", "title"],
            "goods_name": ["goods_name", "product_name_cn", "name_cn"],
            "gender": ["gender", "sex"],                                # ← 新增
        },
        "name_like_cols": ["goods_name", "product_name"],
    },
        "geox": {
        "table": "geox_inventory",
        "fields": {
            "channel_item_id": "channel_item_id",
            "product_code": ["product_code", "product_name", "code"],
            "size": ["size", "product_size"],
            "title_en": ["product_title", "title_en", "title"],
            "goods_name": ["goods_name", "product_name_cn", "name_cn"],
            "gender": ["gender", "sex"],                                # ← 新增
        },
        "name_like_cols": ["goods_name", "product_name"],
    },


    # ✅ 新增 ECCO
    "ecco": {
        "table": "ecco_inventory",  # 或 "ECCO_inventory"，Postgres 会自动转小写，不加引号都可以
        "fields": {
            "channel_item_id": "channel_item_id",
            "product_code": ["product_code", "product_name", "code"],
            "size": ["size", "product_size"],
            "title_en": ["product_title", "title_en", "title"],
            # ECCO 表里没有 goods_name，可以用描述做兜底
            "goods_name": ["product_description", "product_title"],
            "gender": ["gender", "sex"],
        },
        # 兜底从哪里拆 code/尺码
        "name_like_cols": ["product_description", "product_title"],
    },
}

# 5) 备案字段顺序（保持不变）
CORRECT_COLUMNS = [
    '货品ID',
    '原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）',
    '规格型号',
    '主要成分',
    '品牌',
    '主要用途',
    '货品英文名称',
    '销售单位（枚举值详见:销售单位列表，代码及中文均支持）',
    '前端宝贝链接',
    '商品备案价（元）',
    'HSCODE(枚举值详见:hscode列表)（海关十位编码）',
    '商品类目',
    '第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）',
    '第一数量（请严格对应第一单位要求填写）',
    '第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）',
    '第二数量（请严格对应第二单位要求填写）',
    '申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）'
]

# 6) 固定项（不改）
HSCODE_FIXED = "6405200090"
ORIGIN = "越南"
SPEC = "1双"
BRAND_FIXED = {
    "camper": "camper",
    "clarks": "clarks",
    "geox":   "geox",
    "ecco":   "ecco",
}

PURPOSE = "衣着用品"
UOM1 = "千克"; QTY1 = 1
UOM2 = "双";   QTY2 = 1
CATEGORY_DEFAULT = "女鞋 / 低帮鞋 / 时尚休闲鞋"  # 仅作历史兼容的默认值

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
def first_existing_val(row: dict, candidates) -> str | None:
    """在 row 中按候选列名优先级返回第一个非空值。"""
    cand_list = candidates if isinstance(candidates, (list, tuple)) else [candidates]
    for c in cand_list or []:
        if c in row and row[c] is not None and str(row[c]).strip():
            return str(row[c]).strip()
    return None

def parse_code_size_from_name(name: str) -> tuple[str | None, str | None]:
    if not name: return None, None
    s = str(name)
    m_code = re.search(r'颜色分类\s*:\s*([^;]+)', s)
    m_size = re.search(r'尺码\s*:\s*([^;]+)', s)
    code = m_code.group(1).strip() if m_code else None
    size = m_size.group(1).strip() if m_size else None
    return code, size

def fetch_db_row(brand: str, goods_id: str) -> dict:
    b = BRAND_MAP[brand]
    table = b["table"]
    ch_field = b["fields"]["channel_item_id"]
    sql = text(f"SELECT * FROM {table} WHERE {ch_field} = :cid LIMIT 1")
    with ENGINE.begin() as conn:
        row = conn.execute(sql, {"cid": str(goods_id).strip()}).mappings().first()
    return dict(row) if row else {}

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
    # 按需接入 offers/定价表，这里默认留空
    return ""

# ----------------------- 性别判定（新增） -----------------------
def _detect_gender(db_row: dict, fields_map: dict, title_en: str, goods_name: str) -> str:
    """
    返回 '男' / '女' / '通用'
    优先库字段 gender/sex；其次标题/中文名兜底；都失败为通用。
    """
    # 1) 数据库字段优先
    gender_val = first_existing_val(db_row, fields_map.get("gender"))
    g = (str(gender_val).strip().lower()) if gender_val is not None else ""
    if g in ("男", "男款", "male", "men", "m"): return "男"
    if g in ("女", "女款", "female", "women", "w"): return "女"

    # 2) 文本兜底（英文/中文关键词）
    text = f"{title_en or ''} {goods_name or ''}".lower()
    # 注意避免把 "women" 里包含 "men" 的误判，先匹配 women 后匹配 men
    if any(x in text for x in ["women ", "women's", "womens", " 女", "女款", "女鞋"]): return "女"
    if any(x in text for x in ["men ", "men's", "mens", " 男", "男款", "男鞋"]): return "男"

    # 3) 实在判不出
    return "通用"

def _category_by_gender(gender_cn: str) -> str:
    if gender_cn == "男":
        return "男鞋 / 低帮鞋 / 时尚休闲鞋"
    if gender_cn == "女":
        return "女鞋 / 低帮鞋 / 时尚休闲鞋"
    return "鞋靴 / 低帮鞋 / 时尚休闲鞋"

# ----------------------- 主行构建 -----------------------
def build_row(brand: str, goods_id: str) -> dict:
    db = fetch_db_row(brand, goods_id)
    fields = BRAND_MAP[brand]["fields"]

    code = first_existing_val(db, fields.get("product_code"))
    size = first_existing_val(db, fields.get("size"))
    title_en = first_existing_val(db, fields.get("title_en"))
    goods_name = first_existing_val(db, fields.get("goods_name"))

    if not (code and size):
        for col in BRAND_MAP[brand]["name_like_cols"]:
            name_val = db.get(col)
            c2, s2 = parse_code_size_from_name(name_val)
            code = code or c2
            size = size or s2
            if code and size: break

    if not title_en and code:
        title_en = read_title_from_txt(brand, code)

    # ⭐ 新增：性别判定 & 动态类目
    gender_cn = _detect_gender(db, fields, title_en or "", goods_name or "")
    category_val = _category_by_gender(gender_cn) if gender_cn else CATEGORY_DEFAULT

    price = fetch_price(brand, code or "", size or "")

    main_component = '67% Textile 33% Recycled Polyester'
    declaration = (
        f'款式：未过踝|'
        f'鞋面材料：织布|'
        f'鞋底材料：EVA|'
        f'品牌（中文或外文名称）：{BRAND_FIXED.get(brand, brand)}|'
        f'货号：{code or ""}'
    )

    row = {
        '货品ID': goods_id,
        '原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）': ORIGIN,
        '规格型号': SPEC,
        '主要成分': main_component,
        '品牌': BRAND_FIXED.get(brand, brand),
        '主要用途': PURPOSE,
        '货品英文名称': title_en or "",
        '销售单位（枚举值详见:销售单位列表，代码及中文均支持）': UOM2,
        '前端宝贝链接': '',
        '商品备案价（元）': price,
        'HSCODE(枚举值详见:hscode列表)（海关十位编码）': HSCODE_FIXED,
        '商品类目': category_val,  # ← 仅此列改为动态
        '第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）': UOM1,
        '第一数量（请严格对应第一单位要求填写）': QTY1,
        '第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）': UOM2,
        '第二数量（请严格对应第二单位要求填写）': QTY2,
        '申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）': declaration
    }
    if not code:
        row['申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）'] += "|⚠缺少货号"
    return row

from pathlib import Path

def generate_shoe_hscode(
    input_list: Path | str = INPUT_LIST,
    output_dir: Path | str = OUTPUT_DIR,
    sheet_name: str = SHEET_NAME
):
    # ✅ 无论传进来是 str 还是 Path，这里强制转成 Path
    input_list = Path(input_list)
    output_dir = Path(output_dir)

    df = pd.read_excel(input_list, dtype=str)
    # 兼容列名
    if "brand" not in df.columns:
        raise KeyError("输入清单必须包含列：brand")

    # ---- 大小写不敏感匹配列名 ----
    lower_cols = {c.lower(): c for c in df.columns}
    candidate_names = ["货品id", "货品ID", "goods_id"]

    gid_col = None
    for name in candidate_names:
        if name.lower() in lower_cols:
            gid_col = lower_cols[name.lower()]
            break

    if gid_col is None:
        raise KeyError("输入清单必须包含列：货品ID（或 goods_id），大小写不敏感。")

    df["brand"] = df["brand"].str.lower().str.strip()

    rows = []
    for i, r in df.iterrows():
        brand = r["brand"]
        goods_id = str(r[gid_col]).strip()
        if brand not in BRAND_MAP:
            print(f"⚠ 跳过第{i+1}行：未知品牌 {brand}")
            continue
        if not goods_id:
            print(f"⚠ 跳过第{i+1}行：空 货品ID")
            continue
        try:
            rows.append(build_row(brand, goods_id))
        except Exception as e:
            print(f"❌ 第{i+1}行失败（brand={brand}, 货品ID={goods_id}）：{e}")

    out_df = pd.DataFrame(rows, columns=CORRECT_COLUMNS)

    # ✅ 这里就安全了，一定是 Path 对象
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"备案导入_{ts}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        out_df.to_excel(w, sheet_name=sheet_name, index=False)

    print(f"✅ 生成完成：{out_path}")


if __name__ == "__main__":
    generate_shoe_hscode()
