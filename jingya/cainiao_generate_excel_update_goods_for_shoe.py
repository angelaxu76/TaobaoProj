# -*- coding: utf-8 -*-
"""
鞋类品牌（camper / clarks_jingya）专用：
- 从品牌 inventory 表读取基础信息（config.BRAND_CONFIG[brand]["TABLE_NAME"]）
- 合并 "货品导出*.xlsx"，生成严格按淘宝菜鸟模板列名/顺序的 Excel：
  列顺序严格为：
    货品编码, 货品名称, 货品名称（英文）, 条形码, 吊牌价, 零售价, 成本价,
    易碎品, 危险品, 温控要求, 效期管理, 有效期（天）, 临期预警（天）,
    禁售天数（天）, 禁收天数（天）, 长, 宽, 高, 毛重, 净重,
    长-运输单元, 宽-运输单元, 高-运输单元, 重量-运输单元, 包含电池

依赖：
- config.BRAND_CONFIG[brand]：包含 PGSQL_CONFIG, TABLE_NAME
- pip：psycopg2, pandas, openpyxl
"""

import os
import re
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import psycopg2
from config import BRAND_CONFIG

# ======================= ✅【参数区】=======================
BRAND = "camper"                         # camper 或 clarks_jingya
GOODS_DIR = Path(r"D:/TB/taofenxiao/goods")
GROUP_SIZE = 500
# ========================================================

# 中文品牌展示名
BRAND_MAP = {
    "camper": "camper看步",
    "clarks_jingya": "clarks其乐",
    "clarks": "clarks其乐",
    "ecco": "ecco爱步",
    "geox": "geox健乐士",
}

# —— 鞋款仅三类：靴子 / 凉鞋 / 休闲鞋（默认）——
BOOTS_KW = [
    "boot", "chelsea", "desert", "chukka", "combat", "ankle", "mid boot", "high boot"
]
SANDALS_KW = [
    "sandal", "flip flop", "flip-flop", "slipper", "slide", "mule"
]

def guess_style_zh_shoes(style_category: str, title: str = "", desc: str = "") -> str:
    """
    只输出三类：靴子 / 凉鞋 / 休闲鞋（默认）
    """
    def hit_any(txt: str, kws) -> bool:
        t = (txt or "").lower()
        return any(k in t for k in kws)

    for src in (style_category, title, desc):
        if hit_any(src, BOOTS_KW):
            return "靴子"
        if hit_any(src, SANDALS_KW):
            return "凉鞋"
    return "休闲鞋"

def normalize_gender_shoes(gender: str) -> str:
    """
    直接使用数据库性别，不做推断：
    男款 -> 男鞋；女款 -> 女鞋；童款 -> 童鞋
    """
    g = (gender or "").strip()
    if g == "男款":
        return "男鞋"
    if g == "女款":
        return "女鞋"
    if g == "童款":
        return "童鞋"
    return g  # 兜底返回原值（极少数情况）

def is_all_zeros(s: str) -> bool:
    s = (s or "").strip()
    return bool(s) and all(ch == "0" for ch in s)

# 解析“货品导出”Excel中常见的“货品名称”格式： 颜色分类: CODE; 尺码: 42
PAT_NAME = re.compile(r"(?:颜色分类|颜色)\s*:\s*([^;]+)\s*;\s*尺码\s*:\s*(.+)")

def export_goods_excel_from_db_shoes(brand: str, goods_dir: Path, group_size: int = 500):
    cfg = BRAND_CONFIG[brand]
    pg = cfg["PGSQL_CONFIG"]
    table_inventory = cfg["TABLE_NAME"]

    # 找最新一份“货品导出*.xlsx”
    candidates = [f for f in os.listdir(goods_dir) if f.startswith("货品导出") and f.endswith(".xlsx")]
    if not candidates:
        raise FileNotFoundError("❌ 未找到以 '货品导出' 开头的 Excel 文件")
    candidates.sort(reverse=True)
    infile = goods_dir / candidates[0]

    # 一次性载入品牌 inventory：构建 (code,size) -> info 映射
    prod: Dict[Tuple[str, str], Dict[str, str]] = {}
    with psycopg2.connect(**pg) as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                product_code,           -- 编码
                size,                   -- 尺码（EU 等）
                COALESCE(gender, '') AS gender,
                COALESCE(product_title, '') AS title,
                COALESCE(style_category, '') AS category,
                COALESCE(product_description, '') AS desc,
                COALESCE(ean, '') AS ean
            FROM {table_inventory}
        """)
        for code, sz, gender, title, cat, desc, ean in cur.fetchall():
            key = (str(code).strip(), str(sz).strip())
            prod[key] = {
                "gender": gender,
                "title": title,
                "category": cat,
                "desc": desc,
                "ean": ean,
            }

    brand_label = BRAND_MAP.get(brand, brand)

    # 读取 Excel
    df = pd.read_excel(infile)
    out_rows = []

    # 兼容列名缺失（有些模板可能没有某列）
    def get_cell(row, col):
        return "" if col not in row or pd.isna(row[col]) else row[col]

    for _, row in df.iterrows():
        raw_name = str(get_cell(row, "货品名称"))
        code_field = str(get_cell(row, "货品编码"))
        barcode_excel = str(get_cell(row, "条形码"))

        m = PAT_NAME.search(raw_name)
        if not m:
            # 解析失败就跳过（也可以扩展更多解析规则）
            continue

        code = m.group(1).strip()
        size = m.group(2).strip()

        info = prod.get((code, size))
        if info is None:
            # 尺码不精确匹配时，尝试仅按 code 兜底（取第一条）
            any_keys = [k for k in prod if k[0] == code]
            if any_keys:
                info = prod[any_keys[0]]
            else:
                continue

        gender_std = normalize_gender_shoes(info.get("gender", ""))
        style_zh = guess_style_zh_shoes(info.get("category", ""), info.get("title", ""), info.get("desc", ""))
        new_name = f"{brand_label}{gender_std}{style_zh}{code}尺码{size}"

        # 条形码优先：Excel 非空 & 非全0；否则用 DB 的 ean
        ean_db = info.get("ean", "")
        barcode_out = barcode_excel
        if not barcode_out or is_all_zeros(barcode_out):
            barcode_out = ean_db

        row_out = {
            "货品编码": code_field,
            "货品名称": new_name,
            "货品名称（英文）": info.get("title", ""),
            "条形码": barcode_out,
            "吊牌价": "", "零售价": "", "成本价": "",
            "易碎品": "", "危险品": "", "温控要求": "",
            "效期管理": "", "有效期（天）": "", "临期预警（天）": "",
            "禁售天数（天）": "", "禁收天数（天）": "",
            "长": 350, "宽": 260, "高": 130, "毛重": 1200, "净重": 900,
            "长-运输单元": "", "宽-运输单元": "", "高-运输单元": "", "重量-运输单元": "",
            "包含电池": ""
        }
        out_rows.append(row_out)

    if not out_rows:
        print("⚠️ 没有可导出的记录（可能“货品名称”格式不是：颜色分类: CODE; 尺码: X）")
        return

    # —— 列顺序严格按之前模板，不增不减不换位 —— 
    cols = [
        "货品编码", "货品名称", "货品名称（英文）", "条形码", "吊牌价", "零售价", "成本价",
        "易碎品", "危险品", "温控要求", "效期管理", "有效期（天）", "临期预警（天）",
        "禁售天数（天）", "禁收天数（天）",
        "长", "宽", "高", "毛重", "净重",
        "长-运输单元", "宽-运输单元", "高-运输单元", "重量-运输单元",
        "包含电池"
    ]

    for i in range(0, len(out_rows), group_size):
        part = out_rows[i:i+group_size]
        out_df = pd.DataFrame(part, columns=cols)
        out_path = goods_dir / f"更新后的货品导入_第{i//group_size+1}组.xlsx"
        # 保持 sheet 名称为“商品信息”
        out_df.to_excel(out_path, sheet_name="商品信息", index=False)
        print(f"✅ 已生成：{out_path}")

if __name__ == "__main__":
    export_goods_excel_from_db_shoes(BRAND, GOODS_DIR, GROUP_SIZE)
