# jingya/generate_binding_goods_excel.py
# -*- coding: utf-8 -*-
import re
import time
import zipfile
from xml.sax.saxutils import escape as xml_escape
import psycopg2
import pandas as pd
import openpyxl
from pathlib import Path
from typing import Dict, Tuple
from config import BRAND_CONFIG, PGSQL_CONFIG
from common.product.size_utils import clean_size_for_barbour
from cainiao.barbour_goods_type import build_barbour_goods_name

# 菜鸟官方「单个商品绑定上传模板」：直接改模板 XML 填数据，生成的文件可直接导入
# （pandas/openpyxl 保存的文件用内联字符串，鲸芽导入不认，见 _write_into_template）
TEMPLATE_FILE = Path("D:/TB/taofenxiao/模版文件/单个商品绑定上传模板.xlsx")
TEMPLATE_SHEET = "单个商品绑定"
# 第 1 行表头、第 2/3 行模板自带提示（菜鸟导入跳过前 3 行），数据从第 4 行开始
# TEMPLATE_TIP_* 仅在找不到模板、走 pandas 直接导出时使用
TEMPLATE_TIP_ROW = 3
TEMPLATE_DATA_START_ROW = 4
TEMPLATE_TIP_VALUES = {
    "*销售渠道": "填写销售渠道名称，请参见下方'销售渠道参考'sheet表",
    "*渠道店铺ID": "填写店铺ID，请参照以下地址https://g.cainiao.com/infra/tao-fuwu/information",
    "*发货模式": "请选择直发或代发",
}

# 仅保留模板的 6 列（按你要求的顺序，“*菜鸟货品ID”放最后）
TEMPLATE_COLUMNS = [
    "*销售渠道", "*渠道店铺ID", "*发货模式",
    "*外部渠道商品ID", "*商品名称", "*菜鸟货品ID",
]

# —— 品牌显示名（Barbour 使用中英组合，便于识别）——
BRAND_MAP  = {
    "clarks": "clarks其乐",
    "camper": "camper看步",
    "clarks": "clarks其乐",
    "ecco": "ecco爱步",
    "geox": "geox健乐士",
    "barbour": "Barbour",
}

# 鞋类风格映射（保持原样）
STYLE_MAP_SHOES = {
    "boots": "靴",
    "sandal": "凉鞋",
    "loafers": "乐福鞋",
    "slip-on": "便鞋",
    "casual": "休闲鞋",
}

# Barbour 服装/帽子等品类匹配见 barbour_goods_type.py

def _parse_code_size_from_goods_name(name: str) -> Tuple[str, str]:
    """
    从 “货品名称” 中解析：颜色分类:CODE;尺码:S    （也兼容 “颜色:CODE”，以及 “尺码:S;颜色分类:CODE” 顺序颠倒）
    单尺码商品（围巾/帽子等）只有 “颜色分类:CODE”，此时返回 (CODE, "")，尺码由调用方从 DB 补。
    """
    s = str(name or "")
    m_code = re.search(r"(?:颜色分类|颜色)\s*[:：]\s*([^;；]+)", s)
    m_size = re.search(r"尺码\s*[:：]\s*([^;；]+)", s)
    if not m_code:
        return "", ""
    return m_code.group(1).strip(), (m_size.group(1).strip() if m_size else "")

def _parse_code_size_from_any(text: str) -> Tuple[str, str]:
    """
    兜底：从 channel_item_id 或任意字符串里解析 (code, size)
    兼容如 K100300-00142 / 26178475-395 / 2617847539540 等写法。
    """
    s = str(text or "")
    m = re.search(r"([A-Za-z]*\d{5,}[-_\.]?\d{0,3})(\d{2,3})?$", s)
    if m:
        return m.group(1) or "", m.group(2) or ""
    m2 = re.search(r"([A-Za-z]*\d{5,})[-_\.]?(\d{1,3})", s)
    if m2:
        return m2.group(1) or "", m2.group(2) or ""
    return "", ""

def _alnum(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(s or ""))

def _fetch_maps(table: str, pgcfg: Dict):
    """
    从品牌 inventory 表拿到：
      - id_to_channel_item: 货品ID(channel_product_id) -> channel_item_id；以及 channel_item_id -> channel_item_id（双路径）
      - item_to_code_size:  channel_item_id -> (code, size_raw)  （注意 size 为源字符串，后续会 normalize）
      - code_size_to_gender_style: (code, size_raw) -> (gender, style_category)  （若无则空）
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
                sz_raw = str(size or "")
                if ch_prod:
                    id_to_channel_item[ch_prod] = ch_item
                if ch_item:
                    id_to_channel_item[ch_item] = ch_item
                    item_to_code_size[ch_item] = (code, sz_raw)
                key = (code, sz_raw)
                if key not in code_size_to_gender_style:
                    code_size_to_gender_style[key] = (str(gender or ""), str(style or ""))
    finally:
        conn.close()
    return id_to_channel_item, item_to_code_size, code_size_to_gender_style

def _fetch_barbour_products(pgcfg: Dict) -> Dict[Tuple[str, str], Dict[str, str]]:
    """
    读取 barbour_products：用 (color_code, clean_size) → {title, gender, category, style_name}
    """
    m: Dict[Tuple[str, str], Dict[str, str]] = {}
    conn = psycopg2.connect(**pgcfg)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT product_code, size, COALESCE(gender,''), COALESCE(title,''), COALESCE(category,''),
                       COALESCE(style_name,'')
                FROM barbour_products
            """)
            for code, sz, gender, title, cat, style_name in cur.fetchall():
                key = (str(code or ""), clean_size_for_barbour(str(sz or "")))
                m[key] = {"gender": gender, "title": title, "category": cat, "style_name": style_name}
    finally:
        conn.close()
    return m

def _build_product_name(brand: str,
                        code: str,
                        size_raw: str,
                        gender_from_inv: str = "",
                        style_from_inv: str = "",
                        bp_title: str = "",
                        bp_gender: str = "",
                        bp_category: str = "",
                        bp_style_name: str = "") -> str:
    """
    统一生成 *商品名称
    - Barbour：按 编码前缀 → 英文名(style_name) → category 逐步匹配商品类型（服装/帽子/…），
      输出：{品牌}{男装/女装/男士/女士}{品类}{编码}尺码{size}（见 barbour_goods_type.py）
    - 其他品牌：保留鞋类逻辑：{品牌}{男鞋/女鞋}{风格}{编码}尺码{size}
    """
    b = (brand or "").lower()
    brand_label = BRAND_MAP.get(b, brand)

    if b == "barbour":
        name, _ = build_barbour_goods_name(
            code, size_raw,
            style_name=bp_style_name or bp_title,
            gender=bp_gender or gender_from_inv,
            category=bp_category,
            brand_label=brand_label,
        )
        return name.replace("None", "")

    # 鞋类
    gender_label = "男鞋" if "男" in (gender_from_inv or bp_gender or "") else "女鞋"
    style_key = (style_from_inv or "").lower()
    style_zh = STYLE_MAP_SHOES.get(style_key, "休闲鞋")
    return f"{brand_label}{gender_label}{style_zh}{code}尺码{size_raw}".replace("None", "")

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

    # Barbour: 预取 barbour_products
    bp_map: Dict[Tuple[str, str], Dict[str, str]] = {}
    if brand == "barbour":
        t = time.time()
        bp_map = _fetch_barbour_products(pgcfg)
        log(f"✓ 读取 barbour_products：{len(bp_map)} 条，用时 {time.time()-t:.2f}s")

    # 固定列
    unbound_df["*销售渠道"] = "淘分销"
    unbound_df["*渠道店铺ID"] = "2221679632348"
    unbound_df["*发货模式"] = "直发"
    unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]
    log("✓ 已填充固定列：*销售渠道 / *渠道店铺ID / *发货模式 / *菜鸟货品ID")

    # —— 先尝试从 Excel 的 “货品名称” 中直接解析 (code, size_raw)
    unbound_df["_code_from_name"], unbound_df["_size_raw_from_name"] = zip(
        *unbound_df.get("货品名称", pd.Series([""]*len(unbound_df))).apply(_parse_code_size_from_goods_name)
    )

    # 再得到 channel_item_id（命中不到就用 货品ID 兜底）
    unbound_df["_ch_item"] = unbound_df["货品ID"].map(id_to_channel_item).fillna(unbound_df["货品ID"])

    # 从 channel_item 映射 (code, size_raw)
    codes_sizes = unbound_df["_ch_item"].map(item_to_code_size)
    def _safe_get_code(cs): return cs[0] if isinstance(cs, (tuple, list)) and len(cs) == 2 and cs[0] is not None else ""
    def _safe_get_size(cs): return cs[1] if isinstance(cs, (tuple, list)) and len(cs) == 2 and cs[1] is not None else ""
    unbound_df["_code_from_map"] = codes_sizes.apply(_safe_get_code)
    unbound_df["_size_raw_from_map"] = codes_sizes.apply(_safe_get_size)

    # 兜底：从 ch_item 文本解析
    # —— 兜底：为所有行预先解析一次（效率足够，也最稳妥），避免列未创建
    parsed_all = unbound_df["_ch_item"].apply(_parse_code_size_from_any)
    unbound_df["_code_fallback"] = [p[0] for p in parsed_all]
    unbound_df["_size_raw_fallback"] = [p[1] for p in parsed_all]

    # —— 选择优先来源：Excel 名称 > DB map > 文本兜底（统一在这里完成，确保一定有列）
    _code_pref_1 = unbound_df["_code_from_name"].fillna("").astype(str)
    _code_pref_2 = unbound_df["_code_from_map"].fillna("").astype(str)
    _code_pref_3 = unbound_df["_code_fallback"].fillna("").astype(str)

    _size_pref_1 = unbound_df["_size_raw_from_name"].fillna("").astype(str)
    _size_pref_2 = unbound_df["_size_raw_from_map"].fillna("").astype(str)
    _size_pref_3 = unbound_df["_size_raw_fallback"].fillna("").astype(str)

    unbound_df["_code"] = _code_pref_1.where(_code_pref_1 != "", _code_pref_2.where(_code_pref_2 != "", _code_pref_3))
    unbound_df["_size_raw"] = _size_pref_1.where(_size_pref_1 != "", _size_pref_2.where(_size_pref_2 != "", _size_pref_3))

    # 统一做编码清洗（仅限 code，尺码的清洗分原始/规范化两种，保持你原设计）
    unbound_df["_code"] = unbound_df["_code"].fillna("").astype(str).map(_alnum)

    # A) 清洗后的尺码（用于名称/DB匹配）
    unbound_df["_size_norm"] = unbound_df["_size_raw"].fillna("").astype(str).apply(clean_size_for_barbour)

    # B) 原始尺码（用于外部渠道商品ID，不改变大小写，仅去掉首尾空格）
    unbound_df["_size_id"] = unbound_df["_size_raw"].fillna("").astype(str).str.strip()

    # 生成 *外部渠道商品ID = 原始编码 + 原始尺码，整体 alnum 清洗（示例：MWX0339NY91 + 2XL → MWX0339NY912XL）
    unbound_df["*外部渠道商品ID"] = (unbound_df["_code"] + unbound_df["_size_id"]).apply(
        lambda x: re.sub(r"[^A-Za-z0-9]", "", str(x))
    )
    null_rate = (unbound_df["*外部渠道商品ID"] == "").mean()
    log(f"✓ 生成 *外部渠道商品ID 完成（alnum清洗后；空值占比 {null_rate:.1%}）")



    # 生成 *商品名称
    def _name_row(row):
        code = row["_code"]
        size_raw = row["_size_raw"]
        size_norm = row.get("_size_norm", "")   # ← 用 get 更安全
        # inventory 提供的性别/风格（鞋类）
        inv_gender, inv_style = code_size_to_gender_style.get((code, row.get("_size_raw_from_map","")), ("", ""))
        # Barbour: 用 bp_map 提升准确性（用 clean_size 匹配）
        bp_title = bp_gender = bp_category = bp_style_name = ""
        if brand == "barbour" and code and size_norm:
            info = bp_map.get((code, size_norm))
            if info is None:
                # 同编码任意尺码兜底
                for (c, s), v in bp_map.items():
                    if c == code:
                        info = v
                        break
            if info:
                bp_title = info.get("title", "")
                bp_gender = info.get("gender", "")
                bp_category = info.get("category", "")
                bp_style_name = info.get("style_name", "")
        return _build_product_name(
            brand=brand,
            code=code,
            size_raw=size_raw,
            gender_from_inv=inv_gender,
            style_from_inv=inv_style,
            bp_title=bp_title,
            bp_gender=bp_gender,
            bp_category=bp_category,
            bp_style_name=bp_style_name
        )

    t = time.time()
    unbound_df["*商品名称"] = unbound_df.apply(_name_row, axis=1)
    log(f"✓ 生成 *商品名称 完成，用时 {time.time()-t:.2f}s")

    # 按 6 列输出
    final_df = unbound_df.reindex(columns=TEMPLATE_COLUMNS)
    log(f"✓ 最终列顺序：{TEMPLATE_COLUMNS}")

    # 写文件
    output_file = goods_dir / "未绑定商品绑定信息.xlsx"
    t = time.time()
    if TEMPLATE_FILE.exists():
        _write_into_template(final_df, output_file)
        log(f"✓ 写入Excel（基于模板 {TEMPLATE_FILE.name}）：{output_file} 用时 {time.time()-t:.2f}s")
        log(f"🎉 全流程完成，总耗时 {time.time()-t0:.2f}s；数据行数={len(final_df)}")
        return output_file
    log(f"⚠ 未找到模板 {TEMPLATE_FILE}，改为直接导出（可能需要手工复制到模板再导入）")

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

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        final_df_with_tip.to_excel(writer, index=False, sheet_name="单个商品绑定")
    log(f"✓ 写入Excel：{output_file} 用时 {time.time()-t:.2f}s")
    log(f"🎉 全流程完成，总耗时 {time.time()-t0:.2f}s；总行数（含提示行）={len(final_df_with_tip)}")
    return output_file

def _write_into_template(final_df: pd.DataFrame, output_file: Path) -> None:
    """
    直接改模板 xlsx 的 XML，生成和 Excel 手工粘贴后一样结构的文件。

    不能用 openpyxl 保存：它把字符串写成内联字符串（inlineStr）、不生成 sharedStrings.xml，
    单元格内容虽然一样，但鲸芽/菜鸟导入读不出来。这里只替换 sheet1 第 4 行起的数据行和
    sharedStrings.xml，模板第 1~3 行（表头/提示）和其他文件逐字节保留。
    """
    # 用 openpyxl 只读表头，确认列顺序（不保存）
    wb = openpyxl.load_workbook(TEMPLATE_FILE, read_only=True)
    header = [c.value for c in next(wb[TEMPLATE_SHEET].iter_rows(min_row=1, max_row=1))]
    wb.close()
    col_letters = {name: chr(ord("A") + i) for i, name in enumerate(header) if name}
    missing = [n for n in TEMPLATE_COLUMNS if n not in col_letters]
    if missing:
        raise ValueError(f"模板表头缺少列：{missing}，实际表头：{header}")
    cols = sorted(TEMPLATE_COLUMNS, key=lambda n: col_letters[n])
    last_col = col_letters[cols[-1]]

    with zipfile.ZipFile(TEMPLATE_FILE) as zin:
        # 定位目标 sheet 的 XML 路径（workbook.xml 的 r:id → workbook.xml.rels 的 Target）
        wb_xml = zin.read("xl/workbook.xml").decode("utf-8")
        rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        rid = re.search(rf'<sheet [^>]*name="{re.escape(TEMPLATE_SHEET)}"[^>]*r:id="([^"]+)"', wb_xml).group(1)
        target = re.search(rf'<Relationship [^>]*Id="{rid}"[^>]*Target="([^"]+)"', rels_xml)
        if not target:
            target = re.search(rf'<Relationship [^>]*Target="([^"]+)"[^>]*Id="{rid}"', rels_xml)
        sheet_path = "xl/" + target.group(1).lstrip("/").replace("xl/", "", 1)

        sheet_xml = zin.read(sheet_path).decode("utf-8")
        sst_xml = zin.read("xl/sharedStrings.xml").decode("utf-8")

        # —— sharedStrings：保留模板原有条目，追加新字符串 ——
        unique_count = len(re.findall(r"<si>", sst_xml))
        new_si, index = [], {}

        def sst_idx(text: str) -> int:
            nonlocal unique_count
            if text not in index:
                index[text] = unique_count
                unique_count += 1
                sp = ' xml:space="preserve"' if text != text.strip() else ""
                new_si.append(f"<si><t{sp}>{xml_escape(text)}</t></si>")
            return index[text]

        # —— 数据行：样式沿用模板示例数据行（第 4 行）的 s 值 ——
        m_tpl_row = re.search(rf'<row r="{TEMPLATE_DATA_START_ROW}"[^>]*>', sheet_xml)
        row_attrs = re.search(r'(?: s="\d+" customFormat="1")', m_tpl_row.group(0)) if m_tpl_row else None
        cell_style = re.search(rf'<c r="A{TEMPLATE_DATA_START_ROW}" s="(\d+)"', sheet_xml)
        cell_s = f' s="{cell_style.group(1)}"' if cell_style else ""
        row_s = row_attrs.group(0) if row_attrs else ""

        rows_xml, n_refs = [], 0
        recs = final_df.to_dict("records")
        for r, rec in enumerate(recs, start=TEMPLATE_DATA_START_ROW):
            cells = []
            for name in cols:
                v = rec.get(name)
                v = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
                ref = f"{col_letters[name]}{r}"
                if v == "":
                    cells.append(f'<c r="{ref}"{cell_s}/>')
                else:
                    cells.append(f'<c r="{ref}"{cell_s} t="s"><v>{sst_idx(v)}</v></c>')
                    n_refs += 1
            rows_xml.append(f'<row r="{r}" spans="1:{len(header)}"{row_s}>{"".join(cells)}</row>')

        # 去掉模板第 4 行起的示例数据，换成新数据
        head, rest = sheet_xml.split("<sheetData>", 1)
        body, tail = rest.split("</sheetData>", 1)
        kept = "".join(
            m.group(0) for m in re.finditer(r"<row [^>]*?(?:/>|>.*?</row>)", body)
            if int(re.search(r'r="(\d+)"', m.group(0)).group(1)) < TEMPLATE_DATA_START_ROW
        )
        last_row = TEMPLATE_DATA_START_ROW + len(recs) - 1 if recs else TEMPLATE_DATA_START_ROW - 1
        head = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:{last_col}{last_row}"/>', head)
        new_sheet_xml = f"{head}<sheetData>{kept}{''.join(rows_xml)}</sheetData>{tail}"

        # sharedStrings 的 count = 所有 t="s" 引用数
        kept_refs = len(re.findall(r't="s"', kept))
        other_refs = 0
        for info in zin.infolist():
            if info.filename.startswith("xl/worksheets/sheet") and info.filename != sheet_path:
                other_refs += len(re.findall(r't="s"', zin.read(info.filename).decode("utf-8")))
        total_count = kept_refs + n_refs + other_refs
        new_sst_xml = re.sub(r'count="\d+"', f'count="{total_count}"', sst_xml, count=1)
        new_sst_xml = re.sub(r'uniqueCount="\d+"', f'uniqueCount="{unique_count}"', new_sst_xml, count=1)
        new_sst_xml = new_sst_xml.replace("</sst>", "".join(new_si) + "</sst>")

        # 其他文件逐字节复制，顺序/压缩方式与模板一致
        with zipfile.ZipFile(output_file, "w") as zout:
            for info in zin.infolist():
                if info.filename == sheet_path:
                    data = new_sheet_xml.encode("utf-8")
                elif info.filename == "xl/sharedStrings.xml":
                    data = new_sst_xml.encode("utf-8")
                else:
                    data = zin.read(info.filename)
                zout.writestr(info, data, compress_type=info.compress_type)


if __name__ == "__main__":
    # 本地快速测试
    generate_channel_binding_excel("barbour", Path("D:/TB/taofenxiao/goods"))
