# jingya/cainiao_generate_excel_binding_goods_jingya.py
# -*- coding: utf-8 -*-
import re
import time
import psycopg2
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Optional
from config import BRAND_CONFIG, PGSQL_CONFIG

# 仅保留模板的 6 列（按你要求的顺序，“*菜鸟货品ID”放最后）
TEMPLATE_COLUMNS = [
    "*销售渠道", "*渠道店铺ID", "*发货模式",
    "*外部渠道商品ID", "*商品名称", "*菜鸟货品ID",
]

# —— 商品名生成（与 cainiao_generate_update_goods_excel 一致）——
BRAND_MAP  = {
    "clarks_jingya": "clarks其乐",
    "camper": "camper看步",
    "clarks": "clarks其乐",
    "ecco": "爱步",
    "geox": "健乐士",
    "barbour": "巴伯尔",
}
STYLE_MAP = {
    "boots": "靴",
    "sandal": "凉鞋",
    "loafers": "乐福鞋",
    "slip-on": "便鞋",
    "casual": "休闲鞋",
}
def build_product_name(brand: str, gender: str, style_en: str, product_code: str, size: str) -> str:
    brand_label = BRAND_MAP.get((brand or "").lower(), brand)
    gender_label = "男鞋" if "男" in (gender or "") else "女鞋"
    style_zh = STYLE_MAP.get((style_en or "").lower(), "休闲鞋")
    # 一定把编码与尺码拼进去
    return f"{brand_label}{gender_label}{style_zh}{product_code}尺码{size}".replace("None", "")

def _clean_join(code: str, size: str) -> str:
    """编码+尺码，去掉非字母数字字符。"""
    return re.sub(r"[^A-Za-z0-9]", "", f"{str(code or '')}{str(size or '')}")

def _parse_code_size_from_any(text: str) -> Tuple[str, str]:
    """
    从 channel_item_id 或任意字符串兜底解析 (product_code, size)。
    兼容如 K100300-00142 / 26178475-395 / 2617847539540 等写法。
    """
    s = str(text or "")
    # 先尝试：编码(字母可选+5位以上数字+可选连接符+最多3位) + 可选尺码(2-3位)
    m = re.search(r"([A-Za-z]*\d{5,}[-_\.]?\d{0,3})(\d{2,3})?$", s)
    if m:
        code = m.group(1) or ""
        size = m.group(2) or ""
        return code, size
    # 再尝试常见 “编码-尺码 / 编码_尺码 / 编码.尺码”
    m2 = re.search(r"([A-Za-z]*\d{5,})[-_\.]?(\d{2,3})", s)
    if m2:
        return m2.group(1) or "", m2.group(2) or ""
    return "", ""

def _fetch_maps(table: str, pgcfg: Dict):
    """
    一次性拉取映射，避免逐行查库：
      - id_to_channel_item: 货品ID(channel_product_id) -> channel_item_id；以及 channel_item_id -> channel_item_id（双路径，最大化命中）
      - item_to_code_size:  channel_item_id -> (product_code, size)
      - code_size_to_gender_style: (product_code, size) -> (gender, style_category)
    """
    id_to_channel_item: Dict[str, str] = {}
    item_to_code_size: Dict[str, Tuple[str, str]] = {}
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
                code = str(product_code or "")
                sz = str(size or "")
                # 双路径：货品ID→item 以及 item→item
                if ch_prod:
                    id_to_channel_item[ch_prod] = ch_item
                if ch_item:
                    id_to_channel_item[ch_item] = ch_item
                    item_to_code_size[ch_item] = (code, sz)
                # 命名映射
                key = (code, sz)
                if key not in code_size_to_gender_style:
                    code_size_to_gender_style[key] = (str(gender or ""), str(style or ""))
    finally:
        conn.close()

    return id_to_channel_item, item_to_code_size, code_size_to_gender_style

def generate_channel_binding_excel(brand: str, goods_dir: Path, debug: bool = True) -> Path:
    t0 = time.time()
    def log(msg):
        if debug:
            print(msg)

    brand = (brand or "").lower()
    cfg = BRAND_CONFIG[brand]
    table_name = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)

    log(f"▶ 开始生成绑定Excel | brand={brand} | table={table_name}")
    goods_dir = Path(goods_dir)
    product_files = list(goods_dir.glob("货品导出*.xlsx"))
    if not product_files:
        raise FileNotFoundError("❌ 未找到以『货品导出』开头的 Excel 文件")
    product_file = product_files[0]
    relation_file = goods_dir / "商货品关系导出.xlsx"
    log(f"✓ 输入文件：{product_file}")
    log(f"✓ 关系文件：{relation_file}（存在={relation_file.exists()}）")

    # 读取原始数据
    t = time.time()
    df_product = pd.read_excel(product_file, dtype=str)
    log(f"✓ 读取货品导出：{len(df_product)} 行，用时 {time.time()-t:.2f}s")

    if relation_file.exists():
        t = time.time()
        df_relation = pd.read_excel(relation_file, dtype=str)
        log(f"✓ 读取商货品关系：{len(df_relation)} 行，用时 {time.time()-t:.2f}s")
    else:
        df_relation = pd.DataFrame(columns=["菜鸟货品ID"])
        log("⚠ 未找到商货品关系文件，默认视为全部未绑定")

    # 已绑定去重（去掉后缀 *1）
    if "菜鸟货品ID" in df_relation.columns:
        before = df_relation["菜鸟货品ID"].nunique(dropna=True)
        df_relation["菜鸟货品ID"] = df_relation["菜鸟货品ID"].str.replace(r"\*1$", "", regex=True)
        bound_ids = df_relation["菜鸟货品ID"].dropna().unique().tolist()
        log(f"✓ 已绑定ID数：{len(bound_ids)}（去重前 {before}）")
    else:
        bound_ids = []
        log("⚠ 关系表无『菜鸟货品ID』列，默认视为全部未绑定")

    unbound_df = df_product[~df_product["货品ID"].isin(bound_ids)].copy()
    log(f"✓ 未绑定待处理：{len(unbound_df)} 行")

    # 预取 DB 映射（一次查询）
    t = time.time()
    id_to_channel_item, item_to_code_size, code_size_to_gender_style = _fetch_maps(table_name, pgcfg)
    log(
        f"✓ DB 映射：id→item {len(id_to_channel_item)}；item→(code,size) {len(item_to_code_size)}；"
        f"(code,size)→(gender,style) {len(code_size_to_gender_style)}，用时 {time.time()-t:.2f}s"
    )

    # 固定列
    unbound_df["*销售渠道"] = "淘分销"
    unbound_df["*渠道店铺ID"] = "2219163936872"
    unbound_df["*发货模式"] = "直发"
    unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]
    log("✓ 已填充固定列：*销售渠道 / *渠道店铺ID / *发货模式 / *菜鸟货品ID")

    # 先得到每行的 channel_item_id（命中不到就用 货品ID 兜底）
    unbound_df["_ch_item"] = unbound_df["货品ID"].map(id_to_channel_item).fillna(unbound_df["货品ID"])

    # 映射出 (code,size)
    codes_sizes = unbound_df["_ch_item"].map(item_to_code_size)

    def _safe_get_code(cs):
        return cs[0] if isinstance(cs, (tuple, list)) and len(cs) == 2 and cs[0] is not None else ""

    def _safe_get_size(cs):
        return cs[1] if isinstance(cs, (tuple, list)) and len(cs) == 2 and cs[1] is not None else ""

    unbound_df["_code"] = codes_sizes.apply(_safe_get_code)
    unbound_df["_size"] = codes_sizes.apply(_safe_get_size)

    # 兜底：对缺失的，从 ch_item 文本解析
    mask_missing = (unbound_df["_code"] == "") | (unbound_df["_size"] == "")
    if mask_missing.any():
        parsed = unbound_df.loc[mask_missing, "_ch_item"].apply(_parse_code_size_from_any)
        unbound_df.loc[mask_missing, "_code"] = [p[0] for p in parsed]
        unbound_df.loc[mask_missing, "_size"] = [p[1] for p in parsed]

    # 规范化：只保留字母数字
    unbound_df["_code"] = unbound_df["_code"].astype(str).str.replace(r"[^A-Za-z0-9]", "", regex=True)
    unbound_df["_size"] = unbound_df["_size"].astype(str).str.replace(r"[^A-Za-z0-9]", "", regex=True)

    # *外部渠道商品ID（vectorized）
    unbound_df["*外部渠道商品ID"] = (unbound_df["_code"] + unbound_df["_size"]).fillna("")
    null_rate = (unbound_df["*外部渠道商品ID"] == "").mean()
    log(f"✓ 生成 *外部渠道商品ID 完成（空值占比 {null_rate:.1%}）")

    # *商品名称（vectorized + DB性别/款式映射）
    def _name_row(row):
        code, size = row["_code"], row["_size"]
        gender, style = code_size_to_gender_style.get((code, size), ("", ""))
        return build_product_name(brand, gender, style, code, size)

    t = time.time()
    unbound_df["*商品名称"] = unbound_df.apply(_name_row, axis=1)
    log(f"✓ 生成 *商品名称 完成，用时 {time.time()-t:.2f}s")

    # 按 6 列输出
    final_df = unbound_df.reindex(columns=TEMPLATE_COLUMNS)
    log(f"✓ 最终列顺序：{TEMPLATE_COLUMNS}")

    # 第一行提示
    tip_row = {
        "*销售渠道": "填写销售渠道名称，请参见下方'销售渠道参考'sheet表",
        "*渠道店铺ID": "填写店铺ID，请参照以下地址https://g.cainiao.com/infra/tao-fuwu/information",
        "*发货模式": "请选择直发或代发",
        "*外部渠道商品ID": "",
        "*商品名称": "",
        "*菜鸟货品ID": "",
    }
    final_df_with_tip = pd.concat(
        [pd.DataFrame([tip_row], columns=TEMPLATE_COLUMNS), final_df],
        ignore_index=True
    )

    # 写文件
    output_file = goods_dir / "未绑定商品绑定信息.xlsx"
    t = time.time()
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        final_df_with_tip.to_excel(writer, index=False, sheet_name="单个商品绑定")
    log(f"✓ 写入Excel：{output_file} 用时 {time.time()-t:.2f}s")
    log(f"🎉 全流程完成，总耗时 {time.time()-t0:.2f}s；总行数（含提示行）={len(final_df_with_tip)}")
    return output_file

if __name__ == "__main__":
    # 本地快速测试
    generate_channel_binding_excel("camper", Path("D:/TB/taofenxiao/goods"))
