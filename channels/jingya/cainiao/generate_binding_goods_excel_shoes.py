# jingya/cainiao_generate_excel_binding_goods_shoes.py
# -*- coding: utf-8 -*-
import re
import time
import psycopg2
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple
from config import BRAND_CONFIG, PGSQL_CONFIG

# ============================================================
# 运行参数（按需修改）
# ============================================================
CHANNEL_NAME    = "淘分销"          # 销售渠道名称
CHANNEL_SHOP_ID = "2221679632348"   # 渠道店铺ID（精雅淘宝店铺ID）
DELIVERY_MODE   = "直发"            # 发货模式
# ============================================================

# 仅保留模板的 6 列（按要求顺序，"*菜鸟货品ID"放最后）
TEMPLATE_COLUMNS = [
    "*销售渠道", "*渠道店铺ID", "*发货模式",
    "*外部渠道商品ID", "*商品名称", "*菜鸟货品ID",
]

BRAND_MAP = {
    "clarks_jingya": "clarks其乐",
    "camper": "camper看步",
    "clarks": "clarks其乐",
    "ecco": "ecco爱步",
    "geox": "geox健乐士",
}

# —— 鞋款三类 —— 
_BOOTS_KW = ["boot", "chelsea", "desert", "chukka", "combat", "ankle"]
_SANDALS_KW = ["sandal", "flip flop", "flip-flop", "slipper", "slide", "mule"]

def _normalize_gender_shoes(gender: str) -> str:
    g = (gender or "").strip()
    if g == "男款": return "男鞋"
    if g == "女款": return "女鞋"
    if g == "童款": return "童鞋"
    return g

def _guess_style_zh_shoes(style_category: str, title: str = "") -> str:
    def hit_any(txt: str, kws) -> bool:
        t = (txt or "").lower()
        return any(k in t for k in kws)
    for src in (style_category, title):
        if hit_any(src, _BOOTS_KW): return "靴子"
        if hit_any(src, _SANDALS_KW): return "凉鞋"
    return "休闲鞋"

def _parse_code_size_from_goods_name(name: str) -> Tuple[str, str]:
    """从货品名称解析：颜色分类:CODE;尺码:S"""
    s = str(name or "")
    m = re.search(r"(?:颜色分类|颜色)\s*:\s*([^;]+)\s*;\s*尺码\s*:\s*(.+)", s)
    if not m: return "", ""
    return m.group(1).strip(), m.group(2).strip()

def _fetch_maps(table: str, pgcfg: Dict):
    """从 inventory 表拿映射：id→item, item→(code,size), (code,size)→(gender,style)"""
    id_to_channel_item, item_to_code_size, code_size_to_info = {}, {}, {}
    conn = psycopg2.connect(**pgcfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT channel_item_id, channel_product_id, product_code, size, gender, style_category
                FROM {table}
            """)
            for ch_item, ch_prod, code, size, gender, style in cur.fetchall():
                ch_item = str(ch_item or "")
                ch_prod = str(ch_prod or "")
                code = str(code or "")
                sz_raw = str(size or "")
                if ch_prod:
                    id_to_channel_item[ch_prod] = ch_item
                if ch_item:
                    id_to_channel_item[ch_item] = ch_item
                    item_to_code_size[ch_item] = (code, sz_raw)
                code_size_to_info[(code, sz_raw)] = (gender, style)
    finally:
        conn.close()
    return id_to_channel_item, item_to_code_size, code_size_to_info

def _build_product_name_shoes(brand: str, code: str, size_raw: str,
                              gender: str, style_category: str, title: str) -> str:
    brand_label = BRAND_MAP.get(brand, brand)
    gender_label = _normalize_gender_shoes(gender)
    style_zh = _guess_style_zh_shoes(style_category, title)
    return f"{brand_label}{gender_label}{style_zh}{code}尺码{size_raw}"

def generate_channel_binding_excel_shoes(brand: str, goods_dir: Path, debug: bool = True) -> Path:
    t0 = time.time()
    def log(msg): 
        if debug: print(msg)

    brand = (brand or "").lower()
    cfg = BRAND_CONFIG[brand]
    table_name = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)

    log(f"▶ 鞋类绑定Excel | brand={brand} | table={table_name}")
    goods_dir = Path(goods_dir)
    product_files = list(goods_dir.glob("货品导出*.xlsx"))
    if not product_files:
        raise FileNotFoundError("❌ 未找到以『货品导出』开头的 Excel 文件")
    product_file = product_files[0]
    relation_file = goods_dir / "商货品关系导出.xlsx"
    log(f"✓ 输入文件：{product_file}")
    log(f"✓ 关系文件：{relation_file}（存在={relation_file.exists()}）")

    # 读取原始数据
    df_product = pd.read_excel(product_file, dtype=str)
    if relation_file.exists():
        df_relation = pd.read_excel(relation_file, dtype=str)
        bound_ids = df_relation.get("菜鸟货品ID", pd.Series([])).dropna().unique().tolist()
    else:
        bound_ids = []

    unbound_df = df_product[~df_product["货品ID"].isin(bound_ids)].copy()
    log(f"✓ 未绑定待处理：{len(unbound_df)} 行")

    # DB 映射
    id_to_channel_item, item_to_code_size, code_size_to_info = _fetch_maps(table_name, pgcfg)

    # 固定列
    unbound_df["*销售渠道"] = CHANNEL_NAME
    unbound_df["*渠道店铺ID"] = CHANNEL_SHOP_ID
    unbound_df["*发货模式"] = DELIVERY_MODE
    unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]

    # 从 Excel 名称解析 code,size
    unbound_df["_code"], unbound_df["_size_raw"] = zip(
        *unbound_df.get("货品名称", pd.Series([""]*len(unbound_df))).apply(_parse_code_size_from_goods_name)
    )

    # 补充 DB 提供的信息
    names = []
    for _, row in unbound_df.iterrows():
        code = row["_code"]
        size_raw = row["_size_raw"]
        inv_gender, inv_style = code_size_to_info.get((code, size_raw), ("", ""))
        name = _build_product_name_shoes(
            brand, code, size_raw,
            inv_gender, inv_style, ""
        )
        names.append(name)
    unbound_df["*商品名称"] = names

    # 外部渠道商品ID = code+size
    unbound_df["*外部渠道商品ID"] = (unbound_df["_code"] + unbound_df["_size_raw"]).apply(
    lambda x: re.sub(r"[^A-Za-z0-9]", "", str(x))
)

    # 按 6 列输出
    final_df = unbound_df.reindex(columns=TEMPLATE_COLUMNS)

    # 第一行提示
    tip_row = {
        "*销售渠道": "填写销售渠道名称",
        "*渠道店铺ID": "填写店铺ID",
        "*发货模式": "请选择直发或代发",
        "*外部渠道商品ID": "",
        "*商品名称": "",
        "*菜鸟货品ID": "",
    }
    final_df_with_tip = pd.concat([pd.DataFrame([tip_row], columns=TEMPLATE_COLUMNS), final_df], ignore_index=True)

    output_file = goods_dir / "未绑定商品绑定信息.xlsx"
    final_df_with_tip.to_excel(output_file, index=False, sheet_name="单个商品绑定")
    log(f"🎉 输出完成：{output_file} 总行数={len(final_df_with_tip)} (含提示行)")
    log(f"总耗时 {time.time()-t0:.2f}s")
    return output_file

if __name__ == "__main__":
    generate_channel_binding_excel_shoes("camper", Path("D:/TB/taofenxiao/goods"))
