# -*- coding: utf-8 -*-
"""
逐 SKU 导出店铺价格（支持批量）
- 单文件：保持 generate_price_excel(brand, input_dir, output_path) 原行为不变（取 input_dir 内“最近修改”的一个Excel）
- 批量：新增 generate_price_excels_bulk(brand, input_dir, output_dir, suffix)
  * 处理 input_dir 下所有 *.xlsx / *.xls
  * 输出文件名 = 输入文件名（不含扩展名） + suffix + ".xlsx"
  * 每个文件独立查价、独立导出，单个失败不影响其它文件
- 列识别：宝贝ID(=item_id)、商家编码(=product_code)、skuID(=skuid)
- 价格来源：品牌表中的 taobao_store_price（优先 product_code；兜底 product_name）
- 输出三列：宝贝id | skuid | 调整后价格
"""
from pathlib import Path
import unicodedata
import re
from typing import List, Dict, Optional, Iterable, Tuple
import pandas as pd
import psycopg2
import math

from config import BRAND_CONFIG

# ===== 列名别名 =====
COL_ALIASES = {
    "item_id": {"item_id","itemid","ITEM_ID","宝贝id","宝贝ID","宝贝Id","宝贝"},
    "product_code": {
        "product_code","productcode","code",
        "商品编码","商品Code","产品编码","编码","货号",
        "商家编码",
        "商家货号","外部编码","外部代码",
        "outer_id","outerid","outer code","outercode"
    },
    "skuid": {
        "skuid","sku_id","SkuId","SKU_ID","SKUID",
        "skuID",
        "渠道货品ID","渠道skuid","货品id","货品ID"
    },
}

_SPLIT = re.compile(r"[,\uFF0C;；\s\r\n]+")


import pandas as pd

import pandas as pd
from pathlib import Path

def _load_blacklist_codes(blacklist_excel_file: str | None) -> set[str]:
    """
    从 blacklist_excel_file 读取黑名单商品编码列表。
    如果 blacklist_excel_file 是 None 或文件不存在，则返回空集合，表示不启用黑名单。
    """
    if not blacklist_excel_file:
        # 没传，等于不启用黑名单
        print("[BLACKLIST] 未提供黑名单文件，黑名单为空")
        return set()

    path_obj = Path(blacklist_excel_file)
    if not path_obj.exists():
        print(f"[BLACKLIST] 黑名单文件不存在: {blacklist_excel_file}，黑名单为空")
        return set()

    df_blk = pd.read_excel(path_obj)

    candidate_cols = [
        "商品编码",
        "product_code",
        "商家编码",
        "外部商品编码",
        "商家货号",
        "货号",
        "编码",
    ]

    col_found = None
    for c in candidate_cols:
        if c in df_blk.columns:
            col_found = c
            break

    if col_found is None:
        print("[BLACKLIST] 未找到可识别的黑名单列，黑名单为空")
        return set()

    codes = (
        df_blk[col_found]
        .astype(str)
        .str.strip()
        .replace({"": pd.NA})
        .dropna()
        .unique()
        .tolist()
    )

    blacklist = {c.upper() for c in codes}
    print(f"[BLACKLIST] 读取到 {len(blacklist)} 个黑名单商品编码")
    return blacklist



import psycopg2
from psycopg2.extras import execute_values

from psycopg2.extras import execute_values

def _fetch_prices_by_code_and_size_bulk(
    conn,
    table: str,
    code_size_pairs: list[tuple[str, str]]
) -> pd.DataFrame:
    """
    批量从 {table} 里拿 (product_code, size) 对应的 taobao_store_price。
    关键点：
    - 不再使用 execute_values（之前只拿到最后一批，导致严重丢价）
    - 手动分批，每批用 WITH wanted AS (VALUES ...) JOIN，逐批执行 cur.execute()
    - 汇总所有批次返回，去重后输出 DataFrame
    """

    # 1. 先把输入规格清洗成稳定字符串键，防止 '16 ' / None 等脏值
    cleaned_pairs = []
    for code, sz in code_size_pairs:
        if code is None or sz is None:
            continue
        c = str(code).strip()
        s = str(sz).strip()
        if c and s:
            cleaned_pairs.append((c, s))

    # 去重，避免同一个 (code,size) 重复查
    unique_pairs = sorted(set(cleaned_pairs))
    if not unique_pairs:
        return pd.DataFrame(columns=["product_code", "size", "taobao_store_price"])

    print(f"[PRICEDEBUG] 待查询组合总数: {len(cleaned_pairs)}，去重后: {len(unique_pairs)}")

    # 2. 分批，每批 50 个 (code,size)
    CHUNK_SIZE = 50
    all_rows: list[tuple[str, str, float]] = []

    with conn.cursor() as cur:
        total_batches = (len(unique_pairs) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for batch_idx, start in enumerate(range(0, len(unique_pairs), CHUNK_SIZE), start=1):
            batch = unique_pairs[start:start + CHUNK_SIZE]

            # 用 mogrify 把每条 (code,size) 变成安全的 SQL ('CODE','SIZE') 片段
            values_sql_list = [
                cur.mogrify("(%s,%s)", (code, size)).decode("utf-8")
                for code, size in batch
            ]
            values_sql_block = ",".join(values_sql_list)

            # 构造本批 SQL
            query_sql = (
                f"WITH wanted(code,size) AS (VALUES {values_sql_block}) "
                f"SELECT t.product_code, t.size, t.taobao_store_price "
                f"FROM {table} t "
                "JOIN wanted w ON t.product_code = w.code AND t.size = w.size"
            )

            # Debug: 打印本批的关键信息（不会太吵）
            print("\n[DEBUG SQL BATCH]")
            print(f"  批次 {batch_idx}/{total_batches}, 本批组合数: {len(batch)}")
            print(f"  示例VALUES前5个: {', '.join(values_sql_list[:5])}")

            # 真正执行
            cur.execute(query_sql)
            batch_rows = cur.fetchall()
            print(f"  -> 本批返回 {len(batch_rows)} 行")

            all_rows.extend(batch_rows)

    print(f"[PRICEDEBUG] 全部分批合计返回 {len(all_rows)} 行")

    # 3. 汇总并去重 (防止同一个 (product_code,size) 多次出现)
    merged_unique = {}
    for (product_code, size, price_val) in all_rows:
        key = (str(product_code).strip(), str(size).strip())
        if key not in merged_unique:
            merged_unique[key] = price_val  # 第一条为准

    rows_for_df = [
        {
            "product_code": pc,
            "size": sz,
            "taobao_store_price": price_val,
        }
        for (pc, sz), price_val in merged_unique.items()
    ]

    df_price = pd.DataFrame(
        rows_for_df,
        columns=["product_code", "size", "taobao_store_price"]
    )

    print(f"[PRICEDEBUG] 去重后最终价格行数: {len(df_price)}")
    return df_price




def _canon(s: str) -> str:
    if s is None: return ""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = s.replace("\u00A0", " ").replace("\u200B", "")
    return s.lower()

def _normalize_col(df: pd.DataFrame, want: str) -> str:
    canon2raw = {_canon(c): c for c in df.columns}
    for alias in COL_ALIASES[want]:
        key = _canon(alias)
        if key in canon2raw:
            return canon2raw[key]
    raise KeyError(f"Excel中缺少必要列：{want}（可用别名：{COL_ALIASES[want]}），当前表头：{list(df.columns)}")

def _list_excels(input_dir: Path) -> List[Path]:
    files = list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

def _find_latest_excel(input_dir: Path) -> Path:
    files = _list_excels(input_dir)
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")
    return files[0]

def _split_skuids(val) -> List[str]:
    if pd.isna(val): return []
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        val = str(int(val))
    s = str(val).strip()
    if not s: return []
    parts = [p.strip() for p in _SPLIT.split(s) if p.strip()]
    parts = [re.sub(r"[^\w\-]", "", p) for p in parts if p]
    return [p for p in parts if p]

def _chunked(it: Iterable, size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf; buf = []
    if buf: yield buf

def _fetch_prices(conn, table: str, codes: List[str]) -> Dict[str, Optional[float]]:
    prices: Dict[str, Optional[float]] = {}
    missing = list(dict.fromkeys(codes))
    with conn.cursor() as cur:
        try:
            for chunk in _chunked(missing, 1000):
                cur.execute(
                    f"SELECT product_code, taobao_store_price FROM {table} "
                    f"WHERE product_code = ANY(%s)", (chunk,))
                for code, price in cur.fetchall():
                    prices[str(code)] = None if price is None else float(price)
            missing = [c for c in missing if c not in prices]
        except Exception:
            pass
        if missing:
            try:
                for chunk in _chunked(missing, 1000):
                    cur.execute(
                        f"SELECT product_name, taobao_store_price FROM {table} "
                        f"WHERE product_name = ANY(%s)", (chunk,))
                    for code, price in cur.fetchall():
                        prices[str(code)] = None if price is None else float(price)
            except Exception:
                pass
    return prices

def _to_text(v: object) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v))):
        return ""
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.15g}"
    if isinstance(v, pd._libs.missing.NAType) or (isinstance(v, str) and v.lower() == "nan"):
        return ""
    return str(v)

# ===== 单文件：保持兼容 =====
def generate_price_excel(
    brand: str,
    input_dir: str | Path,
    output_path: str | Path,
    drop_rows_without_price: bool = True
) -> Path:
    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")
    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir = Path(input_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    excel_file = _find_latest_excel(input_dir)
    print(f"📄 使用输入文件：{excel_file}")
    return _generate_price_excel_from_file(brand, excel_file, output_path, drop_rows_without_price, table, pg)

# ===== 批量：处理 input_dir 下所有 Excel =====
def generate_price_excels_bulk(
    brand: str,
    input_dir: str,
    output_dir: str,
    suffix: str = "_价格",
    drop_rows_without_price: bool = True,
    blacklist_excel_file: str | None = None,
):
    """
    从 input_dir 中批量读取店铺 Excel（每个代表一个店铺），
    调用 _generate_price_excel_from_file() 生成对应价格表，
    并输出到 output_dir。

    新增参数:
        blacklist_excel_file: 黑名单 Excel 的绝对路径。
                              如果提供，则会过滤掉黑名单商品编码。
                              如果为 None，则不启用黑名单。
    """

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 数据库配置
    from config import BRAND_CONFIG
    pgsql_config = BRAND_CONFIG[brand]["PGSQL_CONFIG"]
    table_name = BRAND_CONFIG[brand]["TABLE_NAME"]

    # 找出目录下所有 Excel 文件
    excel_files = list(input_dir.glob("*.xlsx"))
    if not excel_files:
        print(f"⚠ 没找到任何 Excel 文件: {input_dir}")
        return

    print(f"[INFO] 共发现 {len(excel_files)} 个输入文件，将生成价格表...")
    print(f"[INFO] 品牌: {brand}")
    print(f"[INFO] 黑名单文件: {blacklist_excel_file or '未启用'}")

    for f in excel_files:
        try:
            print(f"\n[START] 处理文件: {f.name}")
            _generate_price_excel_from_file(
                file_path=str(f),
                output_dir=str(output_dir),
                brand=brand,
                pgsql_config=pgsql_config,
                blacklist_excel_file=blacklist_excel_file,
                table_name=table_name,
            )
        except Exception as e:
            print(f"[ERROR] 处理 {f.name} 失败: {e}")

    print(f"\n✅ 所有文件处理完成。输出路径: {output_dir}")





import pandas as pd
from pathlib import Path

def _normalize_input_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    我们需要拿到三列：
    - item_id   (宝贝id)
    - skuid     (SKU唯一标识，渠道货品ID)
    - sku_spec  (sku规格，比如 'MWX0339OL71,M')

    这个函数的作用是：从各种可能的列名里抽取并标准化成这三列。
    """

    # 可能的列名映射
    item_id_candidates = ["宝贝id", "宝贝ID", "item_id", "itemid", "itemId", "商品ID", "item id"]
    skuid_candidates   = ["skuid", "SKU ID", "skuID", "SKUId", "渠道货品ID", "渠道货品id", "货品id", "sku id"]
    spec_candidates    = ["sku规格", "SKU规格", "规格", "sku spec", "销售属性"]

    colmap = {}

    # 找 item_id
    for c in item_id_candidates:
        if c in df.columns:
            colmap["item_id"] = c
            break
    # 找 skuid
    for c in skuid_candidates:
        if c in df.columns:
            colmap["skuid"] = c
            break
    # 找 sku_spec
    for c in spec_candidates:
        if c in df.columns:
            colmap["sku_spec"] = c
            break

    missing = [name for name in ["item_id","skuid","sku_spec"] if name not in colmap]
    if missing:
        print("⚠ 输入Excel缺少必要列:", missing)
        # 我们还是尽量返回一些列，后面会 dropna
    # 复制一份只保留我们关心的列，并重命名
    df2 = df.copy()
    out = pd.DataFrame()
    out["item_id"] = df2[colmap["item_id"]] if "item_id" in colmap else pd.NA
    out["skuid"]   = df2[colmap["skuid"]]   if "skuid"   in colmap else pd.NA
    out["sku_spec"]= df2[colmap["sku_spec"]]if "sku_spec"in colmap else pd.NA

    return out


def _split_spec_value(spec_val: str) -> tuple[str|None, str|None]:
    """
    把 'MWX0339OL71,M' 这种值拆成 ('MWX0339OL71','M')
    要求：第一个逗号前 = 商品编码
          第一个逗号后 = 尺码
    如果没有逗号，或为空，返回 (None, None)
    """
    if not isinstance(spec_val, str):
        return (None, None)
    raw = spec_val.strip()
    if raw == "":
        return (None, None)
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 2:
        # 没有尺码信息，视为无效
        return (None, None)
    code_part = parts[0].strip().upper()
    size_part = parts[1].strip()
    if code_part == "" or size_part == "":
        return (None, None)
    return (code_part, size_part)





def _clean_spec_key(spec_val):
    if not isinstance(spec_val, str):
        return None
    v = spec_val.strip()
    return v if v else None


def _generate_price_excel_from_file(
    file_path: str,
    output_dir: str,
    brand: str,
    pgsql_config: dict,
    blacklist_excel_file: str | None,
    table_name: str = "barbour_inventory",
):
    print(f"\n[START] 正在处理文件: {file_path}")

    # 1. 黑名单
    blacklist_codes = _load_blacklist_codes(blacklist_excel_file)

    # 2. 读输入Excel并标准化列
    df_raw = pd.read_excel(file_path)
    print(f"[STATS] 原始Excel行数 df_raw: {len(df_raw)}")

    df_norm = _normalize_input_columns(df_raw)
    # 期望: item_id, skuid, sku_spec
    print(f"[STATS] 规范化后 df_norm(初始) 行数: {len(df_norm)}")

    # 2.1 按excel结构向下填充宝贝ID
    df_norm["item_id"] = df_norm["item_id"].ffill()

    # 2.2 把 item_id 转成字符串，避免科学计数法
    def _item_id_to_str(val):
        if pd.isna(val):
            return ""
        if isinstance(val, (int, float)):
            ival = int(val)
            return str(ival)
        return str(val).strip()

    df_norm["item_id"] = df_norm["item_id"].map(_item_id_to_str)

    print(f"[STATS] df_norm(填充宝贝ID+转字符串后) 行数: {len(df_norm)}")
    print(f"[INFO] 输入列: {list(df_norm.columns)}")
    print("[INFO] 样例数据 (ffill+字符串化后):")
    print(df_norm.head(10))

    # 3. sku_spec -> code_part / size_part
    pairs = df_norm["sku_spec"].map(_split_spec_value)
    df_norm["code_part"] = [p[0] for p in pairs]   # 商品编码 (如 MWX0339OL71 / 也可能是 '海军蓝')
    df_norm["size_part"] = [p[1] for p in pairs]   # 尺码 (如 'M' / '10')
    df_norm["spec_key"]  = df_norm["sku_spec"].map(_clean_spec_key)

    before_drop = len(df_norm)
    df_norm = df_norm.dropna(subset=["code_part", "size_part"])
    after_drop = len(df_norm)
    print(f"[STATS] dropna(code_part/size_part): {before_drop} -> {after_drop}")

    # 4. 黑名单过滤：整款不要
    if len(blacklist_codes) > 0:
        before_blk = len(df_norm)
        df_norm = df_norm[~df_norm["code_part"].isin(blacklist_codes)]
        after_blk = len(df_norm)
        print(f"[STATS] 黑名单过滤: {before_blk} -> {after_blk}")
    else:
        print("[STATS] 黑名单未启用，跳过过滤")

    # 5. 展开 skuid
    # skuid 有可能是 "111,222,333" 这种复合，也可能本来就一行一个
    rows = []
    for _, r in df_norm.iterrows():
        this_item_id = r["item_id"]        # 已经 ffill + str
        this_code    = r["code_part"]
        this_size    = r["size_part"]
        skus_raw     = r["skuid"]
        sku_list     = _split_skuids(skus_raw)

        # debug: 看看有没有行根本解析不出 skuid
        if not sku_list:
            # 打印一次，这行没有有效 skuid，会被丢
            # （注意别打太多，只打前10个）
            if len(rows) < 10:
                print(f"[WARN] 空SKU行? item_id={this_item_id}, code={this_code}, size={this_size}, raw_skuid={skus_raw}")

        for one_sku in sku_list:
            if one_sku:
                rows.append({
                    "item_id":   this_item_id,
                    "skuid":     one_sku,
                    "code_part": this_code,
                    "size_part": this_size,
                })

    df_expanded = pd.DataFrame(
        rows,
        columns=["item_id", "skuid", "code_part", "size_part"]
    )
    print(f"[STATS] 展开后 df_expanded 行数: {len(df_expanded)}")
    if not df_expanded.empty:
        print(df_expanded.head(10))
    else:
        print(f"[WARN] {file_path} 经过拆分后没有任何有效 SKU 行，跳过")
        return

    # 6. 批量查价格 (code_part + size_part)
    conn = psycopg2.connect(**pgsql_config)
    try:
        pairs_for_price = list(zip(df_expanded["code_part"], df_expanded["size_part"]))
        print(f"[STATS] 需要查价的唯一(code_part,size_part)组合数量: {len(set(pairs_for_price))}")
        df_price = _fetch_prices_by_code_and_size_bulk(
            conn,
            table_name,
            pairs_for_price
        )
    finally:
        conn.close()

    print(f"[STATS] df_price(数据库返回价格) 行数: {len(df_price)}")
    if not df_price.empty:
        print(df_price.head(10))

    # 7. 合并价格
    df_merged = df_expanded.merge(
        df_price,
        left_on=["code_part", "size_part"],
        right_on=["product_code", "size"],
        how="left"
    )
    print(f"[STATS] 合并后 df_merged 行数: {len(df_merged)}")
    # 统计一下多少没有价
    missing_price_mask = df_merged["taobao_store_price"].isna()
    missing_cnt = int(missing_price_mask.sum())
    have_cnt = len(df_merged) - missing_cnt
    print(f"[STATS] df_merged 中有价 {have_cnt} 行 / 无价 {missing_cnt} 行")

    # 你当前要求：无价行必须丢掉，不允许空价格出现在输出Excel
    df_merged = df_merged.dropna(subset=["taobao_store_price"])
    print(f"[STATS] 丢掉无价后 df_merged 行数: {len(df_merged)}")

    # 8. 选出最终三列
    df_final = df_merged[["item_id", "skuid", "taobao_store_price"]].copy()
    print(f"[STATS] df_final(初选三列) 行数: {len(df_final)}")

    df_final = df_final.rename(columns={
        "item_id": "宝贝id",
        "skuid": "skuid",
        "taobao_store_price": "调整后价格",
    })

    # 9. 去重 skuid
    before_dedup = len(df_final)
    df_final = df_final.drop_duplicates(subset=["skuid"], keep="first")
    after_dedup = len(df_final)
    print(f"[STATS] 去重skuid: {before_dedup} -> {after_dedup}")

    # 10. 再保险：宝贝id 导出时是字符串
    df_final["宝贝id"] = df_final["宝贝id"].astype(str)

    print("[INFO] df_final 预览:")
    print(df_final.head(20))

    # 11. 写excel
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src_name = Path(file_path).stem
    out_path = out_dir / f"{src_name}_price.xlsx"

    df_final.to_excel(out_path, index=False)
    print(f"[DONE] 已生成价格Excel: {out_path}")
    print(f"[STATS] 写入Excel的最终行数: {len(df_final)}")










# ===== 新增：批量导出 SKU 库存 =====
def generate_stock_excels_bulk(
    brand: str,
    input_dir: str | Path,
    output_dir: str | Path,
    suffix: str = "_库存",
    in_stock_qty: int = 3,
    out_stock_qty: int = 0,
):
    """
    批量根据 input_dir 下的店铺导出表生成“SKUID | 调整后库存”的 Excel。
    规则与 generate_price_excels_bulk 保持一致：仅按 product_code 合并，全款同值。
    - 数据来源：<TABLE_NAME> 中的 taobao_store_price 字段：
        * '有货'  -> in_stock_qty（默认3）
        * 其他/空 -> out_stock_qty（默认0）
    - 输出：<输入文件名+suffix>.xlsx，只有两列：SKUID, 调整后库存
    """
    import pandas as pd
    import psycopg2
    from pathlib import Path

    def _to_text(v):
        if v is None:
            return ""
        s = str(v).strip()
        return s

    def _list_excels(input_dir: Path):
        return (list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls")))

    def status_to_qty_from_price(val: str) -> int:
        # 按你要求：如果 taobao_store_price 字段文本为“有货” => 3，否则 => 0
        #（注意：如果该字段在某些品牌是“数字价格”，此映射会失真，需要改回 stock_status）
        s = _to_text(val)
        return in_stock_qty if s == "有货" else out_stock_qty

    brand = brand.lower().strip()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌：{brand}")
    cfg   = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    pg    = cfg["PGSQL_CONFIG"]

    input_dir  = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 拉取“可售状态”并做映射（仅按 product_code）
    conn = psycopg2.connect(**pg)
    try:
        df_flag = pd.read_sql(f'SELECT product_code, taobao_store_price FROM {table}', conn)
    finally:
        conn.close()

    if "product_code" not in df_flag.columns:
        raise RuntimeError(f"{table} 缺少 product_code 列")

    df_flag["product_code"] = df_flag["product_code"].astype(str).str.strip()
    # 统一映射为数量
    df_flag["调整后库存"] = df_flag["taobao_store_price"].map(status_to_qty_from_price)
    # 按款聚合（若同一款多行，取最大——等价“只要有一行有货则有货”）
    qty_by_code = (
        df_flag.groupby("product_code")["调整后库存"].max()
               .reset_index()
    )

    # 2) 扫描输入目录
    files = _list_excels(input_dir)
    if not files:
        raise FileNotFoundError(f"目录没有找到 Excel：{input_dir}")

    results = []
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            df0 = pd.read_excel(f, dtype=object)

            # 复用你现有的列名别名解析
            col_item = _normalize_col(df0, "item_id")        # 宝贝id
            col_code = _normalize_col(df0, "product_code")   # 商家编码
            col_sku  = _normalize_col(df0, "skuid")          # skuID

            # 展开 SKU 行（与价格导出一致：只按 product_code 合并，不看尺码）
            rows = []
            for _, r in df0.iterrows():
                item_id = _to_text(r.get(col_item))
                code    = _to_text(r.get(col_code))
                skus    = _split_skuids(r.get(col_sku))
                for sid in skus:
                    sid = _to_text(sid)
                    if sid:
                        rows.append((item_id, code, sid))

            if not rows:
                raise ValueError(f"{f.name} 无有效 SKU 记录（检查宝贝ID/商家编码/skuID）。")

            df_expanded = pd.DataFrame(rows, columns=["宝贝id", "product_code", "skuid"])
            df_expanded["product_code"] = df_expanded["product_code"].astype(str).str.strip()

            # 仅按 product_code 合并库存数量（与价格导出相同合并粒度）
            df_tmp = df_expanded.merge(qty_by_code, on="product_code", how="left")
            df_tmp["调整后库存"] = df_tmp["调整后库存"].fillna(out_stock_qty).astype(int)

            # 输出两列
            out_df = df_tmp[["skuid", "调整后库存"]]
            out_name = f.stem + (suffix or "")
            if not out_name.endswith(".xlsx"):
                out_name += ".xlsx"
            out_path = output_dir / out_name
            out_df.to_excel(out_path, index=False)

            print(f"✅ {f.name} -> {out_name} (rows={len(out_df)})")
            results.append((str(f), str(out_path), len(out_df), None))
        except Exception as e:
            print(f"❌ 处理失败：{f} | 错误：{e}")
            results.append((str(f), None, 0, str(e)))

    return results



if __name__ == "__main__":
    # 用法一：单文件（保持兼容）
    #   python this_script.py <brand> <input_dir> <output_excel_path>
    # 用法二：批量（推荐你现在的场景）
    #   python this_script.py <brand> <input_dir> <output_dir> --bulk [--suffix "_价格"]
    import sys, traceback
    try:
        if len(sys.argv) >= 5 and sys.argv[4] == "--bulk":
            brand = sys.argv[1]
            input_dir = sys.argv[2]
            output_dir = sys.argv[3]
            suffix = "_价格"
            if len(sys.argv) >= 7 and sys.argv[5] == "--suffix":
                suffix = sys.argv[6]
            results = generate_price_excels_bulk(brand, input_dir, output_dir, suffix=suffix, drop_rows_without_price=True)
            ok = [r for r in results if r[1] is not None]
            bad = [r for r in results if r[1] is None]
            print(f"📦 批量完成：成功 {len(ok)} 个，失败 {len(bad)} 个")
            if bad:
                print("失败清单：")
                for f, _, err in bad:
                    print(f" - {f} -> 错误：{err}")
        elif len(sys.argv) >= 4:
            generate_price_excel(sys.argv[1], sys.argv[2], sys.argv[3])
        else:
            print("用法：")
            print("  单文件：python this_script.py <brand> <input_dir> <output_excel_path>")
            print('  批  量：python this_script.py <brand> <input_dir> <output_dir> --bulk [--suffix "_价格"]')
    except Exception as e:
        print("❌ 失败：", e)
        traceback.print_exc()
