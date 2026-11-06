# -*- coding: utf-8 -*-
"""
从一张清单（brand + 货品ID）连库生成备案导入 Excel（Barbour 服装版，无模板）。
- 仅需提供：清单 Excel（两列：brand、货品ID 或 goods_id）
- 其他信息从数据库取
- HSCODE 按性别（服装）；帽子/兜帽固定 6505009900，字段见 build_hat_row
- 商品类型按 编码前缀 → 英文名 → category 逐步匹配（见 barbour_goods_type.py）；
  只有 HSCODE_SUPPORTED_TYPES 里的类型才生成备案行，其他类型（包/围巾…）
  暂未配置海关编码，跳过并记录到日志 + 跳过清单 Excel
"""

import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from cainiao.barbour_goods_type import classify_barbour_goods
from cainiao.barbour_material import extract_outer_composition
from cainiao.extract_goods_brand_from_order_excels import parse_code_from_goods_name
from cainiao.hscode_audit import hscode_issue, report_hscode_audit
from common.utils.logger_utils import setup_logger

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

HSCODE_MAP = {
    "女": "6102300000",
    "男": "6101909000",
}

# 已配置海关编码的商品类型（classify_barbour_goods 返回的 goods_type）。
# 包/围巾等拿到 HSCODE 和申报要素后再加进来，没加之前一律跳过。
HAT_GOODS_TYPES = {"帽子", "兜帽"}
HSCODE_SUPPORTED_TYPES = {"服装"} | HAT_GOODS_TYPES
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

# 帽子/兜帽（参照已备案成功的 MHO0004RU52）
HAT_HSCODE = "6505009900"
HAT_ORIGIN = "越南"
HAT_SPEC = "一个"
HAT_MAIN_COMPONENT = "纯棉100%"   # 商品描述提取不到成分时的默认值
HAT_UOM1 = "个"
HAT_CATEGORY = "服饰配件/皮带/帽子/围巾 / 帽子"
HAT_KNITTED_STYLES = {"毛线帽"}   # 其余按机织申报

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

import re

import re

def _normalize_gender(val: str | None) -> str:
    if not val:
        return "男"

    s = str(val).strip().lower()

    # ✅ 先判女（避免 women 包含 men 的误判）
    if ("女款" in s) or ("女" in s):
        return "女"
    if re.search(r"\b(women|woman|women's|womens|ladies|lady|female|girl|girls)\b", s):
        return "女"

    # ✅ 再判男
    if ("男款" in s) or ("男" in s):
        return "男"
    if re.search(r"\b(men|man|men's|mens|male|boy|boys)\b", s):
        return "男"

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

class SkipGoods(Exception):
    """该货品暂不生成备案行（如商品类型未配置海关编码）"""

    def __init__(self, reason: str, info: dict):
        super().__init__(reason)
        self.reason = reason
        self.info = info


def build_row(brand: str, goods_id: str, order_name: str = "", order_sku: str = "") -> dict:
    b = BRAND_MAP[brand]
    fields = b["fields"]

    db = fetch_db_row(brand, goods_id)

    # ① 先从 inventory 拿 product_code（你说这列现在都统一叫 product_code）
    code = first_existing_val(db, fields.get("product_code"))
    if not code:
        code = fetch_fallback_code(brand, db)
    if not code:
        # 同一货号可能有多个货品ID，库存表只存了其中一个；此时用订单信息生成
        code = parse_code_from_goods_name(order_name)
        if not code:
            raise ValueError("缺少货号" if db else "库存表查不到该货品ID，订单名称也解析不出货号")
        print(f"ℹ 货品ID={goods_id} 库存表查不到货号，按订单货号 {code} 生成")

    # ② 用 product_code 去 barbour_products 查商品信息（gender/title/style_category）
    prod = fetch_product_row_by_code(brand, code)

    # ✅ 性别：只信 barbour_products（按你的要求）
    gender_raw = (prod.get("gender") or order_name)
    gender_norm = _normalize_gender(gender_raw)

    # ✅ 商品类型：未配置海关编码的类型跳过（不再一律按大衣申报）
    style_name = prod.get("style_name") or ""
    goods_type, _, style_zh = classify_barbour_goods(
        code, style_name, gender_raw, prod.get("category") or ""
    )
    # 前缀/英文名都没识别出来（如鞋、香水）时 style_zh 为兜底 "服装"，同样视为未配置
    if goods_type not in HSCODE_SUPPORTED_TYPES or style_zh == "服装":
        raise SkipGoods(
            f"商品类型[{goods_type}/{style_zh}]未配置海关编码",
            {"goods_type": goods_type, "style_zh": style_zh,
             "product_code": code, "style_name": style_name},
        )

    hscode = HSCODE_MAP.get(gender_norm, HSCODE_MAP["男"])

    category = _category_from_gender(gender_norm)
    bracket_label, bracket_value = _gender_label_for_decl(gender_norm)

    # ✅ 标题：优先 products，其次 TXT 兜底
    title_en = (prod.get("product_title") or prod.get("title_en") or prod.get("title")
                or prod.get("style_name") or "")
    if not title_en:
        title_en = read_title_from_txt(brand, code)

    # GTIN/EAN（仍从 inventory 拿也行）
    gtin = first_existing_val(db, fields.get("gtin")) or ""

    if goods_type in HAT_GOODS_TYPES:
        # 帽子的 GTIN 取 skuid（已备案样例如此，ean 为空）
        descriptions = fetch_product_descriptions(brand, code) + [db.get("product_description")]
        main_component = extract_outer_composition(descriptions) or HAT_MAIN_COMPONENT
        return build_hat_row(brand, goods_id, code, title_en, gtin or db.get("skuid") or order_sku,
                             style_zh, main_component)

    # # ✅ 按男女分配不同 HS code（你之前的需求）
    # hscode = "6202309000" if gender_norm == "女" else "6201309000"

    # 备案价
    price = fetch_price(brand, code, "")

    filling = ""

    declaration = (
        f"类别（{bracket_label}）:{bracket_value}|"
        f"货号:{code}|"
        f"出口享惠情况:{PREF_EXPORT}|"
        f"种类（大衣、短大衣、斗篷等）:{DECL_KIND}|"
        f"GTIN:{gtin}|"
        f"面料成分含量:{MAIN_COMPONENT}|"
        f"织造方法（机织等）:{WEAVE_METHOD}|"
        f"品牌类型:{BRAND_TYPE}|"
        f"如有填充物，请注明成分含量:{filling}|"
        f"品牌（中文或外文名称）:BARBOUR"
    )

    # 🔎 自检：product_code 查不到 products 时给警告（这会直接解释为什么全是男）
    if not prod:
        print(f"⚠ barbour_products 未找到 product_code={code} (goods_id={goods_id})，gender按订单名称判断，判断不出默认男")

    row = {
        '*货品ID': goods_id,
        '*原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）': ORIGIN,
        '*规格型号': SPEC,
        '*主要成分': MAIN_COMPONENT,
        '*品牌': BRAND_FIXED.get(brand, brand),
        '*主要用途': PURPOSE,
        '*货品英文名称': title_en,
        '*销售单位（枚举值详见:销售单位列表，代码及中文均支持）': UOM1,
        '*前端宝贝链接': '',
        '*商品备案价（元）': price,
        '*HSCODE(枚举值详见:hscode列表)（海关十位编码）': hscode,  # ✅ 改这里
        '*商品类目': category,
        '*第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）': UOM1,
        '*第一数量（请严格对应第一单位要求填写）': QTY1,
        '*第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）': UOM2,
        '*第二数量（请严格对应第二单位要求填写）': QTY2,
        '*申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）': declaration
    }
    return row

def build_hat_row(brand: str, goods_id: str, code: str, title_en: str, gtin: str,
                  style_zh: str, main_component: str) -> dict:
    weave = "针织" if style_zh in HAT_KNITTED_STYLES else WEAVE_METHOD
    declaration = (
        f"货号:{code}|"
        f"出口享惠情况:{PREF_EXPORT}|"
        f"GTIN:{gtin}|"
        f"品牌类型:{BRAND_TYPE}|"
        f"制作工艺（针织、机织等）:{weave}|"
        f"品牌（中文或外文名称）:{BRAND_FIXED.get(brand, brand)}"
    )
    return {
        '*货品ID': goods_id,
        '*原产国/地区(枚举值详见:国别列表)（当原产国为日本时，须标明县市，详见国别列表）': HAT_ORIGIN,
        '*规格型号': HAT_SPEC,
        '*主要成分': main_component,
        '*品牌': BRAND_FIXED.get(brand, brand),
        '*主要用途': PURPOSE,
        '*货品英文名称': title_en,
        '*销售单位（枚举值详见:销售单位列表，代码及中文均支持）': HAT_UOM1,
        '*前端宝贝链接': '',
        '*商品备案价（元）': fetch_price(brand, code, ""),
        '*HSCODE(枚举值详见:hscode列表)（海关十位编码）': HAT_HSCODE,
        '*商品类目': HAT_CATEGORY,
        '*第一单位(枚举值详见:hscode列表)（第一单位由hscode决定）（填写文字或代码）': HAT_UOM1,
        '*第一数量（请严格对应第一单位要求填写）': QTY1,
        '*第二单位(枚举值详见:hscode列表)（第二单位由hscode决定）（填写文字或代码）': UOM2,
        '*第二数量（请严格对应第二单位要求填写）': QTY2,
        '*申报要素(枚举值详见:hscode列表)（要素内容由hscode决定）': declaration,
    }


def fetch_product_descriptions(brand: str, product_code: str) -> list[str]:
    """同一货号在 barbour_products 可能有多条来源记录，取全部描述。"""
    table = BRAND_MAP[brand]["fallback"]["table"]
    sql = text(f"""
        SELECT product_description
        FROM {table}
        WHERE product_code = :code AND product_description IS NOT NULL
        ORDER BY id
    """)
    with ENGINE.begin() as conn:
        return [r[0] for r in conn.execute(sql, {"code": product_code})]


def fetch_product_row_by_code(brand: str, product_code: str) -> dict:
    """
    用 inventory 的 product_code 去 barbour_products 找商品信息（gender/title/style_category等）
    注意：你说已统一列名为 product_code，所以这里按 product_code 精确匹配。
    """
    if not product_code:
        return {}

    b = BRAND_MAP[brand]
    fb = b.get("fallback") or {}
    table = fb.get("table") or "barbour_products"

    sql = text(f"""
        SELECT *
        FROM {table}
        WHERE product_code = :code
        LIMIT 1
    """)
    with ENGINE.begin() as conn:
        row = conn.execute(sql, {"code": str(product_code).strip()}).mappings().first()
    return dict(row) if row else {}


def generate_barbour_hscode(
    input_list: Path | str = INPUT_LIST,
    output_dir: Path | str = OUTPUT_DIR,
    sheet_name: str = SHEET_NAME
):
    # ---- 统一转换为 Path，兼容 pipeline 传入 str ----
    input_list = Path(input_list)
    output_dir = Path(output_dir)

    df = pd.read_excel(input_list, dtype=str)

    # 校验 brand 列
    if "brand" not in df.columns:
        raise KeyError("输入清单必须包含列：brand")

    # ---- 大小写不敏感匹配货品ID列 ----
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

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = setup_logger(
        name="barbour_hscode",
        log_dir=str(output_dir / "logs"),
        filename="barbour_hscode.log",
    )

    rows = []
    skipped = []
    issues = []
    for i, r in df.iterrows():
        brand = r["brand"]
        goods_id = "" if pd.isna(r[gid_col]) else str(r[gid_col]).strip()

        if brand != "barbour":
            print(f"⚠ 跳过第{i+1}行：仅支持 brand=barbour，收到 {brand}")
            issues.append(hscode_issue(goods_id, str(brand), "生成 Barbour 备案", "品牌不是 barbour"))
            continue

        if not goods_id:
            print(f"⚠ 跳过第{i+1}行：空 货品ID")
            issues.append(hscode_issue("", brand, "生成 Barbour 备案", f"清单第{i+1}行货品ID为空"))
            continue

        try:
            order_name = "" if pd.isna(r.get("货品名称")) else str(r.get("货品名称"))
            order_sku = "" if pd.isna(r.get("货品编码")) else str(r.get("货品编码"))
            rows.append(build_row(brand, goods_id, order_name, order_sku))
        except SkipGoods as e:
            msg = (f"跳过 货品ID={goods_id} 货号={e.info['product_code']} "
                   f"({e.info['style_name']})：{e.reason}")
            print(f"⏭ {msg}")
            logger.info(msg)
            skipped.append({"货品ID": goods_id, "货号": e.info["product_code"],
                            "英文名": e.info["style_name"], "商品类型": e.info["goods_type"],
                            "品类": e.info["style_zh"], "跳过原因": e.reason})
            issues.append(hscode_issue(goods_id, brand, "生成 Barbour 备案",
                                       f"{e.reason}（货号={e.info['product_code']}）"))
        except Exception as e:
            print(f"❌ 第{i+1}行失败（brand={brand}, 货品ID={goods_id}）：{e}")
            issues.append(hscode_issue(goods_id, brand, "生成 Barbour 备案", str(e)))

    out_df = pd.DataFrame(rows, columns=CORRECT_COLUMNS)

    out_path = output_dir / f"备案导入_barbour_{ts}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        out_df.to_excel(w, sheet_name=sheet_name, index=False)

    print(f"✅ 生成完成：{out_path}（{len(rows)} 行）")
    logger.info(f"生成完成：{out_path}（{len(rows)} 行，跳过 {len(skipped)} 行）")

    if skipped:
        skip_path = output_dir / f"备案跳过清单_barbour_{ts}.xlsx"
        pd.DataFrame(skipped).to_excel(skip_path, index=False)
        print(f"⚠ 跳过 {len(skipped)} 个未配置海关编码的货品，清单：{skip_path}")
        print(f"  日志：{output_dir / 'logs' / 'barbour_hscode.log'}")

    return {"generated_ids": {row['*货品ID'] for row in rows}, "issues": issues}


if __name__ == "__main__":
    result = generate_barbour_hscode()
    report_hscode_audit(OUTPUT_DIR, (), result["generated_ids"], result["issues"])
