import os
import re
import pandas as pd
import psycopg2
from pathlib import Path
from config import BRAND_CONFIG
from common_taobao.size_utils import clean_size_for_barbour

# ======================= ✅【参数配置区】=======================
BRAND = "barbour"                     # 这里默认做 Barbour 服装
GOODS_DIR = Path("D:/TB/taofenxiao/goods")
GROUP_SIZE = 500
# =============================================================

BRAND_MAP = {
    "barbour": "barbour巴伯尔",
    "clarks_jingya": "clarks其乐",
    "camper": "camper看步",
    "clarks": "clarks其乐",
    "ecco": "ecco爱步",
    "geox": "geox健乐士",
}

# 服装类关键字 → 中文款式（简单映射，可随时补充）
STYLE_MAP_CLOTHING = {
    "wax": "蜡棉夹克", "jacket": "夹克", "jackets": "夹克",
    "quilt": "菱格夹克", "gilet": "马甲", "vest": "马甲",
    "coat": "大衣", "parka": "派克大衣", "anorak": "防风外套",
    "shirt": "衬衫", "t-shirt": "T恤", "polo": "POLO衫",
    "sweater": "毛衣", "knit": "针织衫", "jumper": "套头衫",
    "hoodie": "连帽卫衣", "sweat": "卫衣", "cardigan": "开衫",
    "trousers": "长裤", "jeans": "牛仔裤", "shorts": "短裤",
    "skirt": "半身裙", "dress": "连衣裙",
    "scarf": "围巾", "hat": "帽", "cap": "帽",
}

def guess_style_zh(text: str) -> str:
    t = (text or "").lower()
    for k, v in STYLE_MAP_CLOTHING.items():
        if k in t:
            return v
    return "外套"

def normalize_gender(g: str, title: str = "") -> str:
    """将 gender 标准化为：男装 / 女装 / ''"""
    src = f"{g} {title}".lower()
    # 英文优先识别
    if any(x in src for x in ["men", "men's", "mens", "male"]): return "男装"
    if any(x in src for x in ["women", "women's", "womens", "female"]): return "女装"
    # 中文兜底
    if "男" in g: return "男装"
    if "女" in g: return "女装"
    return ""  # 不确定则留空（需要的话可返回“中性/童装”）

def is_all_zeros(s: str) -> bool:
    return bool(s) and all(ch == "0" for ch in s.strip())

def export_goods_excel_from_db(brand: str, goods_dir: Path, group_size: int = 500):
    cfg = BRAND_CONFIG[brand]
    pg = cfg["PGSQL_CONFIG"]

    # 找最新一份“货品导出*.xlsx”
    candidates = [f for f in os.listdir(goods_dir) if f.startswith("货品导出") and f.endswith(".xlsx")]
    if not candidates:
        raise FileNotFoundError("❌ 未找到以 '货品导出' 开头的 Excel 文件")
    candidates.sort(reverse=True)
    infile = goods_dir / candidates[0]

    # 读 barbour_products（一次性）
    prod = {}
    with psycopg2.connect(**pg) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT color_code, size, COALESCE(gender,''), COALESCE(title,''), COALESCE(category,'')
            FROM barbour_products
        """)
        for code, sz, gender, title, cat in cur.fetchall():
            key = (str(code), clean_size_for_barbour(str(sz)))
            prod[key] = {"gender": gender, "title": title, "category": cat}

    brand_label = BRAND_MAP.get(brand, brand)

    # 读取 Excel
    df = pd.read_excel(infile)
    out_rows = []

    # 既支持 “颜色分类:CODE;尺码:S” 也支持 “颜色:CODE;尺码:S”
    pat = re.compile(r"(?:颜色分类|颜色)\s*:\s*([^;]+)\s*;\s*尺码\s*:\s*(.+)")

    for _, row in df.iterrows():
        raw = str(row.get("货品名称", ""))  # 原列名就是“货品名称”
        code_field = str(row.get("货品编码", ""))
        barcode = str(row.get("条形码", ""))

        m = pat.search(raw)
        if not m:
            continue

        color_code = m.group(1).strip()
        size_raw = m.group(2).strip()
        size_norm = clean_size_for_barbour(size_raw)

        # 先按 (code,size_norm) 精确找；找不到再仅按 code 找任意尺码的信息兜底
        info = prod.get((color_code, size_norm))
        if info is None:
            # fallback：同编码取第一条
            any_keys = [k for k in prod.keys() if k[0] == color_code]
            if any_keys:
                info = prod[any_keys[0]]
            else:
                # 数据库没有这件商品，跳过
                continue

        gender_std = normalize_gender(info.get("gender",""), info.get("title",""))
        style_zh = guess_style_zh(info.get("category","") or info.get("title",""))

        new_name = f"{brand_label}{gender_std}{style_zh}{color_code}尺码{size_raw}"

        row_out = {
            "货品编码": code_field,
            "货品名称": new_name,
            "货品名称（英文）": info.get("title",""),
            "条形码": barcode,   # Barbour 当前无 EAN 合并逻辑；以后加列再合并
            "吊牌价": "", "零售价": "", "成本价": "",
            "易碎品": "", "危险品": "", "温控要求": "",
            "效期管理": "", "有效期（天）": "", "临期预警（天）": "",
            "禁售天数（天）": "", "禁收天数（天）": "",
            "长": 400, "宽": 300, "高": 70, "毛重": 1200, "净重": 900,
            "长-运输单元": "", "宽-运输单元": "", "高-运输单元": "", "重量-运输单元": "",
            "包含电池": ""
        }
        out_rows.append(row_out)

    if not out_rows:
        print("⚠️ 没有可导出的记录")
        return

    cols = [
        "货品编码", "货品名称", "货品名称（英文）", "条形码", "吊牌价", "零售价", "成本价",
        "易碎品", "危险品", "温控要求", "效期管理", "有效期（天）", "临期预警（天）",
        "禁售天数（天）", "禁收天数（天）",
        "长", "宽", "高", "毛重", "净重",
        "长-运输单元", "宽-运输单元", "高-运输单元", "重量-运输单元",
        "包含电池"
    ]

    for i in range(0, len(out_rows), GROUP_SIZE):
        part = out_rows[i:i+GROUP_SIZE]
        out_df = pd.DataFrame(part, columns=cols)
        out_path = goods_dir / f"更新后的货品导入_第{i//GROUP_SIZE+1}组.xlsx"
        out_df.to_excel(out_path, sheet_name="商品信息", index=False)
        print(f"✅ 已生成：{out_path}")

if __name__ == "__main__":
    export_goods_excel_from_db(BRAND, GOODS_DIR, GROUP_SIZE)
