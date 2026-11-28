# -*- coding: utf-8 -*-
"""
从一张清单（brand + 货品ID）连库生成备案导入 Excel（TOAST 版）。

HSCODE / 申报要素完全参照 Barbour（generate_hscode_excel_barbour.py），只有两处不同：
  - 原产国统一 "越南"（服装和帽子都是）
  - 商品信息取自 toast_inventory（按 货品ID=channel_item_id 找货号，再按货号取 类目/英文名/性别）

商品类型见 toast_goods_type.py：服装 → 按性别 HSCODE；帽子 → 6505009900；
其他（包/围巾/袜子/首饰…）未配置海关编码，跳过并记录到日志 + 跳过清单 Excel（与 Barbour 一致）。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from cainiao import generate_hscode_excel_barbour as bb
from cainiao.barbour_material import extract_outer_composition
from cainiao.extract_goods_brand_from_order_excels import parse_code_from_goods_name
from cainiao.hscode_audit import hscode_issue, report_hscode_audit
from cainiao.toast_goods_type import classify_toast_goods
from common.utils.logger_utils import setup_logger

# ======================= ✅【参数配置区】=======================
INPUT_LIST = Path(r"D:\TB\taofenxiao\海关备案\toast.xlsx")
OUTPUT_DIR = Path(r"D:\TB\taofenxiao\海关备案")
SHEET_NAME = "sheet1"

TABLE = "toast_inventory"
BRAND = "toast"
BRAND_DECL = "TOAST"     # 申报要素里的品牌（Barbour 写 BARBOUR）
ORIGIN = "越南"           # 服装、帽子统一

# 与 Barbour 相同：只有服装、帽子生成备案行
HAT_GOODS_TYPES = {"帽子"}
HSCODE_SUPPORTED_TYPES = {"服装"} | HAT_GOODS_TYPES
# =============================================================


def _is_valid_gtin(v) -> bool:
    s = str(v or "").strip()
    return bool(s) and set(s) != {"0"}      # toast 部分 ean 为 0000000000000 占位


def fetch_inventory_row(goods_id: str) -> dict:
    sql = text(f"SELECT * FROM {TABLE} WHERE channel_item_id = :cid LIMIT 1")
    with bb.ENGINE.begin() as conn:
        row = conn.execute(sql, {"cid": str(goods_id).strip()}).mappings().first()
    return dict(row) if row else {}


def fetch_product_by_code(code: str) -> dict:
    """同货号任取一条（类目/英文名/性别/材质同货号一致），优先有有效 ean 的"""
    sql = text(f"""
        SELECT * FROM {TABLE} WHERE product_code = :code
        ORDER BY (ean IS NULL OR ean = '' OR ean ~ '^0+$'), id LIMIT 1
    """)
    with bb.ENGINE.begin() as conn:
        row = conn.execute(sql, {"code": code}).mappings().first()
    return dict(row) if row else {}


def build_row(goods_id: str, order_name: str = "", order_sku: str = "") -> dict:
    inv = fetch_inventory_row(goods_id)

    code = (inv.get("product_code") or "").strip()
    if not code:
        # 同一货号可能有多个货品ID，库存表只存了其中一个；此时用订单信息生成
        code = parse_code_from_goods_name(order_name)
        if not code:
            raise ValueError("缺少货号" if inv else "库存表查不到该货品ID，订单名称也解析不出货号")
        print(f"ℹ 货品ID={goods_id} 库存表查不到货号，按订单货号 {code} 生成")

    prod = inv if inv.get("product_code") else fetch_product_by_code(code)
    if not prod:
        print(f"⚠ {TABLE} 未找到 product_code={code} (goods_id={goods_id})，gender按订单名称判断，判断不出默认男")

    title_en = prod.get("product_title") or ""
    category_en = prod.get("style_category") or ""
    gender_raw = prod.get("gender") or order_name

    goods_type, _, style_zh = classify_toast_goods(category_en, title_en, prod.get("gender") or "")
    # 类目/英文名都没识别出来时 style_zh 为兜底 "服装"，同样视为未配置（与 Barbour 一致）
    if goods_type not in HSCODE_SUPPORTED_TYPES or style_zh == "服装":
        raise bb.SkipGoods(
            f"商品类型[{goods_type}/{style_zh}]未配置海关编码",
            {"goods_type": goods_type, "style_zh": style_zh, "product_code": code, "style_name": title_en},
        )

    gtin = next((g for g in (inv.get("ean"), prod.get("ean")) if _is_valid_gtin(g)), "")

    if goods_type in HAT_GOODS_TYPES:
        main_component = (extract_outer_composition([prod.get("product_material"), prod.get("product_description")])
                          or bb.HAT_MAIN_COMPONENT)
        row = bb.build_hat_row(BRAND, goods_id, code, title_en,
                               gtin or inv.get("skuid") or order_sku, style_zh, main_component)
        row[bb.CORRECT_COLUMNS[1]] = ORIGIN
        row[bb.CORRECT_COLUMNS[-1]] = row[bb.CORRECT_COLUMNS[-1]].replace(
            f"品牌（中文或外文名称）:{BRAND}", f"品牌（中文或外文名称）:{BRAND_DECL}")
        return row

    # —— 服装：与 Barbour build_row 相同 ——
    gender_norm = bb._normalize_gender(gender_raw)
    hscode = bb.HSCODE_MAP.get(gender_norm, bb.HSCODE_MAP["男"])
    bracket_label, bracket_value = bb._gender_label_for_decl(gender_norm)
    declaration = (
        f"类别（{bracket_label}）:{bracket_value}|"
        f"货号:{code}|"
        f"出口享惠情况:{bb.PREF_EXPORT}|"
        f"种类（大衣、短大衣、斗篷等）:{bb.DECL_KIND}|"
        f"GTIN:{gtin}|"
        f"面料成分含量:{bb.MAIN_COMPONENT}|"
        f"织造方法（机织等）:{bb.WEAVE_METHOD}|"
        f"品牌类型:{bb.BRAND_TYPE}|"
        f"如有填充物，请注明成分含量:|"
        f"品牌（中文或外文名称）:{BRAND_DECL}"
    )
    c = bb.CORRECT_COLUMNS
    return {
        c[0]: goods_id,
        c[1]: ORIGIN,
        c[2]: bb.SPEC,
        c[3]: bb.MAIN_COMPONENT,
        c[4]: BRAND,
        c[5]: bb.PURPOSE,
        c[6]: title_en,
        c[7]: bb.UOM1,
        c[8]: "",
        c[9]: bb.fetch_price(BRAND, code, ""),
        c[10]: hscode,
        c[11]: bb._category_from_gender(gender_norm),
        c[12]: bb.UOM1,
        c[13]: bb.QTY1,
        c[14]: bb.UOM2,
        c[15]: bb.QTY2,
        c[16]: declaration,
    }


def generate_toast_hscode(input_list: Path | str = INPUT_LIST,
                          output_dir: Path | str = OUTPUT_DIR,
                          sheet_name: str = SHEET_NAME):
    input_list, output_dir = Path(input_list), Path(output_dir)
    df = pd.read_excel(input_list, dtype=str)
    if "brand" not in df.columns:
        raise KeyError("输入清单必须包含列：brand")
    lower_cols = {c.lower(): c for c in df.columns}
    gid_col = next((lower_cols[n] for n in ("货品id", "goods_id") if n in lower_cols), None)
    if gid_col is None:
        raise KeyError("输入清单必须包含列：货品ID（或 goods_id），大小写不敏感。")
    df["brand"] = df["brand"].str.lower().str.strip()

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = setup_logger(name="toast_hscode", log_dir=str(output_dir / "logs"), filename="toast_hscode.log")

    rows, skipped, issues = [], [], []
    stage = "生成 TOAST 备案"
    for i, r in df.iterrows():
        brand = r["brand"]
        goods_id = "" if pd.isna(r[gid_col]) else str(r[gid_col]).strip()
        if brand != BRAND:
            print(f"⚠ 跳过第{i+1}行：仅支持 brand=toast，收到 {brand}")
            issues.append(hscode_issue(goods_id, str(brand), stage, "品牌不是 toast"))
            continue
        if not goods_id:
            print(f"⚠ 跳过第{i+1}行：空 货品ID")
            issues.append(hscode_issue("", brand, stage, f"清单第{i+1}行货品ID为空"))
            continue
        try:
            order_name = "" if pd.isna(r.get("货品名称")) else str(r.get("货品名称"))
            order_sku = "" if pd.isna(r.get("货品编码")) else str(r.get("货品编码"))
            rows.append(build_row(goods_id, order_name, order_sku))
        except bb.SkipGoods as e:
            msg = f"跳过 货品ID={goods_id} 货号={e.info['product_code']} ({e.info['style_name']})：{e.reason}"
            print(f"⏭ {msg}")
            logger.info(msg)
            skipped.append({"货品ID": goods_id, "货号": e.info["product_code"], "英文名": e.info["style_name"],
                            "商品类型": e.info["goods_type"], "品类": e.info["style_zh"], "跳过原因": e.reason})
            issues.append(hscode_issue(goods_id, brand, stage, f"{e.reason}（货号={e.info['product_code']}）"))
        except Exception as e:
            print(f"❌ 第{i+1}行失败（brand={brand}, 货品ID={goods_id}）：{e}")
            issues.append(hscode_issue(goods_id, brand, stage, str(e)))

    out_path = output_dir / f"备案导入_toast_{ts}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        pd.DataFrame(rows, columns=bb.CORRECT_COLUMNS).to_excel(w, sheet_name=sheet_name, index=False)
    print(f"✅ 生成完成：{out_path}（{len(rows)} 行）")
    logger.info(f"生成完成：{out_path}（{len(rows)} 行，跳过 {len(skipped)} 行）")

    if skipped:
        skip_path = output_dir / f"备案跳过清单_toast_{ts}.xlsx"
        pd.DataFrame(skipped).to_excel(skip_path, index=False)
        print(f"⚠ 跳过 {len(skipped)} 个未配置海关编码的货品，清单：{skip_path}")

    return {"generated_ids": {row[bb.CORRECT_COLUMNS[0]] for row in rows}, "issues": issues}


if __name__ == "__main__":
    result = generate_toast_hscode()
    report_hscode_audit(OUTPUT_DIR, (), result["generated_ids"], result["issues"])
