# jingya/cainiao_generate_excel_binding_goods_jingya.py
# -*- coding: utf-8 -*-
import re
import psycopg2
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Optional
from config import BRAND_CONFIG, PGSQL_CONFIG

# 仅保留你模板的 6 列
TEMPLATE_COLUMNS = [
    "*销售渠道", "*渠道店铺ID",
    "*发货模式", "*外部渠道商品ID", "*商品名称","*菜鸟货品ID",
]

# —— 商品名生成（与 cainiao_generate_update_goods_excel 一致）——
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
    # 一定把编码与尺码拼进去
    return f"{brand_label}{gender_label}{style_zh}{product_code}尺码{size}".replace("None", "").replace("尺码", "尺码")

def _clean_join(code: str, size: str) -> str:
    """编码+尺码，去掉非字母数字字符。"""
    return re.sub(r"[^A-Za-z0-9]", "", f"{str(code or '')}{str(size or '')}")

def _parse_code_size_from_any(text: str) -> Tuple[str, str]:
    """
    从 channel_item_id 或字符串里兜底解析 (product_code, size)。
    兼容如 K100300-00142 / 26178475-395 等写法。
    """
    s = str(text or "")
    # 先尝试：编码(字母可选+5位以上数字+可选连接符+最多3位) + 可选尺码(2-3位)
    m = re.search(r"([A-Za-z]*\d{5,}[-_\.]?\d{0,3})(\d{2,3})?$", s)
    if m:
        code = m.group(1) or ""
        size = m.group(2) or ""
        return code, size
    # 再尝试常见 “编码-尺码” 或 “编码_尺码”
    m2 = re.search(r"([A-Za-z]*\d{5,})[-_\.]?(\d{2,3})", s)
    if m2:
        return m2.group(1) or "", m2.group(2) or ""
    return "", ""

def _fetch_maps(table: str, pgcfg: Dict) -> Tuple[Dict[str, str], Dict[Tuple[str, str], Tuple[str, str]]]:
    """
    返回：
      id_to_channel_item:
        - 货品ID(channel_product_id) -> channel_item_id
        - 以及 channel_item_id -> channel_item_id（兼容“货品ID就是channel_item_id”的情况）
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
                ch_item = str(channel_item_id or "")
                ch_prod = str(channel_product_id or "")
                # 两条映射都建立，最大化命中率
                if ch_prod:
                    id_to_channel_item[ch_prod] = ch_item
                if ch_item:
                    id_to_channel_item[ch_item] = ch_item
                key = (str(product_code or ""), str(size or ""))
                if key not in code_size_to_gender_style:
                    code_size_to_gender_style[key] = (str(gender or ""), str(style or ""))
    finally:
        conn.close()
    return id_to_channel_item, code_size_to_gender_style

def _lookup_code_size_by_channel_item(table: str, pgcfg: Dict, channel_item_id: str) -> Optional[Tuple[str, str]]:
    if not channel_item_id:
        return None
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

    # 固定字段（这三项按你要求写死）
    unbound_df["*销售渠道"] = "淘分销"
    unbound_df["*渠道店铺ID"] = "2219163936872"
    unbound_df["*发货模式"] = "直发"
    unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]

    # *外部渠道商品ID
    def make_channel_item(row) -> str:
        prod_id = str(row.get("货品ID", "")).strip()
        ch_item = id_to_channel_item.get(prod_id, prod_id)  # 兜底：直接用 货品ID
        # 优先 DB 反查 code/size
        pair = _lookup_code_size_by_channel_item(table_name, pgcfg, ch_item)
        if pair:
            code, size = pair
        else:
            # 兜底从 ch_item 文本解析
            code, size = _parse_code_size_from_any(ch_item)
        return _clean_join(code, size) if (code or size) else _clean_join(ch_item, "")

    unbound_df["*外部渠道商品ID"] = unbound_df.apply(make_channel_item, axis=1)

    # *商品名称
    def make_item_name(row) -> str:
        prod_id = str(row.get("货品ID", "")).strip()
        ch_item = id_to_channel_item.get(prod_id, prod_id)
        # 先拿 code/size
        code, size = "", ""
        pair = _lookup_code_size_by_channel_item(table_name, pgcfg, ch_item)
        if pair:
            code, size = pair
        if not (code and size):
            c2, s2 = _parse_code_size_from_any(ch_item)
            code = code or c2
            size = size or s2
        # gender/style
        gender, style = code_size_to_gender_style.get((code, size), ("", ""))
        return build_product_name(brand, gender, style, re.sub(r"[^A-Za-z0-9]", "", code), re.sub(r"[^A-Za-z0-9]", "", size))

    unbound_df["*商品名称"] = unbound_df.apply(make_item_name, axis=1)

    # 按 6 列输出
    final_df = unbound_df.reindex(columns=TEMPLATE_COLUMNS)

    # 在  final_df 生成后插入提示行
    tip_row = {
        "*销售渠道": "填写销售渠道名称，请参见下方'销售渠道参考'sheet表",
        "*渠道店铺ID": "填写店铺ID，请参照以下地址https://g.cainiao.com/infra/tao-fuwu/information",
        "*发货模式": "请选择直发或代发",
        "*外部渠道商品ID": "",
        "*商品名称": "",
        "*菜鸟货品ID": ""
    }

    # 把提示行 DataFrame 拼到最前面
    final_df_with_tip = pd.concat(
        [pd.DataFrame([tip_row], columns=TEMPLATE_COLUMNS), final_df],
        ignore_index=True
    )

    # 然后写 final_df_with_tip，而不是 final_df
    output_file = goods_dir / "未绑定商品绑定信息.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        final_df_with_tip.to_excel(writer, index=False, sheet_name="单个商品绑定")

    print(f"✅ 已生成严格对齐模板格式的文件：{output_file}")
    return output_file

if __name__ == "__main__":
    generate_channel_binding_excel("clarks_jingya", Path("D:/TB/taofenxiao/goods"))
