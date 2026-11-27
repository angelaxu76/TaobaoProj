"""
生成商品文案（卖点1、卖点2、推荐理由、短标题、宝贝名称），不写数据库。输出：
  商品文案_*.xlsx            审核用，可直接修改
  淘宝素材导入_{店铺}_*.xlsx  按淘宝「基础素材」模板，每店一个，图片列留空
改完审核 Excel 后，把 CODES_EXCEL 和 REUSE_EXCEL 都设成该文件再运行，即按修改后的内容重新输出导入文件。
淘宝商品ID 来自 run_import_data 导入的店铺数据，店铺上新后先重跑 analytics/pipeline/run_import_data.py。
运行：python -m ops.creative.run_generate_copy_excel     需要环境变量 DEEPSEEK_API_KEY
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from creative.copywriting.copy_excel import read_copy_excel, write_copy_excel
from creative.copywriting.service import generate_for_brand
from creative.copywriting.taobao_import import write_taobao_import
from creative.store_items import build_store_items

# ==== 参数 ====
BRANDS = ["camper", "clarks", "geox", "barbour"]      # 可多个：camper clarks ecco geox barbour toast
CODES_EXCEL: Path | None = None        # 只处理 Excel 里的商品（列：商品编码 或 渠道产品ID），None = 按 SCOPE
SCOPE = "published"    # published = 已发布；in_stock = 有库存；all = 全部
SOURCE = "db"          # db = 数据库里的描述/特征/颜色（推荐）；txt = 品牌 TXT_DIR 下的 TXT
REUSE_EXCEL: Path | None = None        # 之前输出（可人工改过）的 Excel：已有文案原样保留，只补新商品和空格
COPY_MODE = "safe"     # safe = 只用可核实的颜色/材质/功能 + 中性短语（推荐，不调用 AI）；ai = AI 撰写（更生动，需人工审核）
USE_AI = True          # ai 模式下 False = 只用规则短语；系列中文名翻译也用它控制（仅 cfg/creative_config.py SERIES_USE_CN=True 时）
LIMIT: int | None = None               # 每个品牌最多多少个，试跑时填 10
STORES: list[str] | None = None        # 要输出导入文件的店铺，如 ["五小剑"]；None = 全部启用的店铺
OUTPUT_DIR = Path(r"D:\TB\Products\creative")
# ==============


def read_codes(path: Path) -> list[str]:
    df = pd.read_excel(path, dtype=str)
    cols = {str(c).strip().lower(): c for c in df.columns}
    col = cols.get("商品编码") or cols.get("渠道产品id")
    if col is None:
        raise ValueError(f"❌ {path} 需要有「商品编码」或「渠道产品ID」列")
    return df[col].dropna().astype(str).str.strip().tolist()


def main():
    codes = read_codes(CODES_EXCEL) if CODES_EXCEL else None
    reuse = read_copy_excel(REUSE_EXCEL) if REUSE_EXCEL else None
    items = []
    for b in BRANDS:
        items += generate_for_brand(b, SOURCE, SCOPE, codes, USE_AI, LIMIT, reuse=reuse, mode=COPY_MODE)
    tag = f"{'_'.join(BRANDS)}_{datetime.now():%Y%m%d_%H%M}"
    store_items = build_store_items([p for p, _ in items], STORES)
    write_copy_excel(items, store_items, OUTPUT_DIR / f"商品文案_{tag}.xlsx")
    write_taobao_import(items, store_items, OUTPUT_DIR, tag)


if __name__ == "__main__":
    main()
