# common_taobao/bindings.py
# -*- coding: utf-8 -*-
"""
自包含：不再依赖《单个商品绑定上传模板.xlsx》，列顺序写死在 TEMPLATE_COLUMNS。
从数据库优先获取信息：
- 用 货品ID -> DB 查 channel_item_id；再用 channel_item_id 反查 product_code/size；
- 生成 *外部渠道商品ID（编码+尺码，去除特殊字符）；
- 生成 *商品名称（与 cainiao_generate_update_goods_excel 一致的规则）；
- 只保留未绑定（对比《商货品关系导出.xlsx》）。
"""
import re
import psycopg2
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Optional
from config import BRAND_CONFIG, PGSQL_CONFIG

# ===== 固定列顺序（来自模板文件提取一次后写死） =====
TEMPLATE_COLUMNS = [
    "*菜鸟货品ID", "*销售渠道", "*渠道店铺ID", "*发货模式", "*外部渠道商品ID",
    "*商品名称", "*商品ID", "*商家编码", "*销售属性", "*标准品牌ID", "*标准品牌名称",
    "*类目ID", "*类目名称", "*属性信息"
]

# ===== 名称构造（可替换为 common_taobao.name_utils.build_product_name） =====
BRAND_MAP  = {
    "clarks_jingya": "clarks其乐",
    "camper": "camper看步",
    "clarks": "clarks其乐",
    "ecco": "爱步",
    "geox": "健乐士",
    "barbour": "巴伯尔"
}
STYLE_MAP = {
    "boots": "靴",
    "sandal": "凉鞋",
    "loafers": "乐福鞋",
    "slip-on": "便鞋",
    "casual": "休闲鞋"
}
def build_product_name(brand: str, gender: str, style_en: str, product_code: str, size: str) -> str:
    brand_label = BRAND_MAP.get((brand or "").lower(), brand)
    gender_label = "男鞋" if "男" in (gender or "") else "女鞋"
    style_zh = STYLE_MAP.get((style_en or "").lower(), "休闲鞋")
    return f"{brand_label}{gender_label}{style_zh}{product_code}尺码{size}"

def _clean_join(code: str, size: str) -> str:
    """编码+尺码，去掉非字母数字字符。"""
    return re.sub(r"[^A-Za-z0-9]", "", f"{str(code or '')}{str(size or '')}")

def _fetch_maps(table: str, pgcfg: Dict) -> Tuple[Dict[str, str], Dict[Tuple[str, str], Tuple[str, str]]]:
    """
    返回：
      id_to_channel_item: 货品ID(channel_product_id) -> channel_item_id
      code_size_to_gender_style: (product_code, size) -> (gender, style_category)
    """
    id_to_channel_item: Dict[str, str] = {}
    code_size_to_gender_style: Dict[Tuple[str, str], Tuple[str, str]] = {}
    conn = psycopg2.connect(**pgcfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT channel_item_id, channel_product_id, product_code, size, gender, style_category
                FROM {table}
            """)
            for channel_item_id, channel_product_id, product_code, size, gender, style in cur.fetchall():
                if channel_product_id:
                    id_to_channel_item[str(channel_product_id)] = str(channel_item_id or "")
                key = (str(product_code or ""), str(size or ""))
                if key not in code_size_to_gender_style:
                    code_size_to_gender_style[key] = (str(gender or ""), str(style or ""))
    finally:
        conn.close()
    return id_to_channel_item, code_size_to_gender_style

def _lookup_code_size_by_channel_item(table: str, pgcfg: Dict, channel_item_id: str) -> Optional[Tuple[str, str]]:
    conn = psycopg2.connect(**pgcfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT product_code, size
                FROM {table}
                WHERE channel_item_id = %s
                LIMIT 1
            """, (channel_item_id,))
            row = cur.fetchone()
            if row:
                return str(row[0] or ""), str(row[1] or "")
    finally:
        conn.close()
    return None

def generate_channel_binding_excel(brand: str, goods_dir: Path) -> Path:
    brand = (brand or "").lower()
    cfg = BRAND_CONFIG[brand]
    table_name = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)

    goods_dir = Path(goods_dir)
    product_files = list(goods_dir.glob("货品导出*.xlsx"))
    if not product_files:
        raise FileNotFoundError("❌ 未找到以『货品导出』开头的 Excel 文件")
    product_file = product_files[0]

    relation_file = goods_dir / "商货品关系导出.xlsx"

    # 读取原始数据
    df_product = pd.read_excel(product_file, dtype=str)
    df_relation = pd.read_excel(relation_file, dtype=str) if relation_file.exists() else pd.DataFrame(columns=["菜鸟货品ID"])

    # 已绑定去重（去掉后缀 *1）
    if "菜鸟货品ID" in df_relation.columns:
        df_relation["菜鸟货品ID"] = df_relation["菜鸟货品ID"].str.replace(r"\*1$", "", regex=True)
        bound_ids = df_relation["菜鸟货品ID"].dropna().unique().tolist()
    else:
        bound_ids = []

    unbound_df = df_product[~df_product["货品ID"].isin(bound_ids)].copy()

    # 预取 DB 映射
    id_to_channel_item, code_size_to_gender_style = _fetch_maps(table_name, pgcfg)

    # 固定字段
    unbound_df["*销售渠道"] = "淘分销"
    unbound_df["*渠道店铺ID"] = "2219163936872"
    unbound_df["*发货模式"] = "直发"
    unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]

    # *外部渠道商品ID
    def make_channel_item(row) -> str:
        prod_id = str(row.get("货品ID", "")).strip()
        ch_item = id_to_channel_item.get(prod_id, "")
        if not ch_item:
            return ""
        pair = _lookup_code_size_by_channel_item(table_name, pgcfg, ch_item)
        if pair:
            code, size = pair
        else:
            # 兜底尝试从 channel_item_id 自身解析
            m = re.search(r"([A-Za-z]*\d{5,}[-_\.]?\d{0,3})(\d{2,3})?$", ch_item)
            if m:
                code = m.group(1) or ""
                size = m.group(2) or ""
            else:
                code, size = ch_item, ""
        return _clean_join(code, size)

    unbound_df["*外部渠道商品ID"] = unbound_df.apply(make_channel_item, axis=1)

    # *商品名称
    def make_item_name(row) -> str:
        prod_id = str(row.get("货品ID", "")).strip()
        ch_item = id_to_channel_item.get(prod_id, "")
        code, size = "", ""
        pair = _lookup_code_size_by_channel_item(table_name, pgcfg, ch_item) if ch_item else None
        if pair:
            code, size = pair
        gender, style = code_size_to_gender_style.get((code, size), ("", ""))
        return build_product_name(brand, gender, style, code, size)

    unbound_df["*商品名称"] = unbound_df.apply(make_item_name, axis=1)

    # 按固定列顺序输出
    final_df = unbound_df.reindex(columns=TEMPLATE_COLUMNS)

    output_file = goods_dir / "未绑定商品绑定信息.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        final_df.to_excel(writer, index=False, sheet_name="单个商品绑定")

    print(f"✅ 已生成严格对齐模板格式的文件：{output_file}")
    return output_file
