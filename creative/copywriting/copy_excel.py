# -*- coding: utf-8 -*-
"""审核用文案 Excel：输出，以及读取之前（人工改过）的 Excel 复用。导入淘宝的文件见 taobao_import.py。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from cfg.creative_config import COPY_LABELS
from creative.copywriting.validator import check_length, claim_evidence, water_level
from creative.product_source import ProductInfo
from creative.store_items import StoreItems

_SOURCE_CN = {"ai": "AI", "mixed": "AI+规则", "rule": "规则", "reuse": "沿用", "safe": "保守"}
_WATER_CN = {"waterproof": "防水", "resistant": "防泼水", "none": "无"}
STORE_ID_PREFIX = "淘宝商品ID@"


def write_copy_excel(items: list[tuple[ProductInfo, dict]], store_items: list[StoreItems], path: Path) -> Path:
    if not items:
        raise ValueError("❌ 没有可输出的文案")
    df = pd.DataFrame([{
        "品牌": p.brand, "渠道产品ID": p.channel_product_id, "商品编码": p.product_code,
        **{STORE_ID_PREFIX + s.folder: ",".join(s.get(p.product_code)) for s in store_items},
        **{lab: r.get(f, "") for f, lab in COPY_LABELS.items()},
        "来源": _SOURCE_CN.get(r["copy_source"], ""), "系列": r["series_en"], "系列中文": r["series_cn"],
        "商品名称": r["category_cn"], "颜色": p.color_cn, "防水等级": _WATER_CN[water_level(p)],
        "功能依据(英文原文)": claim_evidence([r.get(f) for f in COPY_LABELS], p), "英文标题": p.title,
    } for p, r in items])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = set(COPY_LABELS.values())
    widths = {"品牌": 9, "渠道产品ID": 16, "商品编码": 20, "来源": 9, "防水等级": 9, "功能依据(英文原文)": 70, "英文标题": 60}
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="文案")
        ws = w.sheets["文案"]
        ws.freeze_panes = "D2"
        for i, name in enumerate(df.columns, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = widths.get(name, 22 if name in labels else 16)
    print(f"✅ 已输出 {len(df)} 个商品：{path}")
    return path


def read_copy_excel(path: Path) -> dict[tuple[str, str], dict]:
    """读取之前输出的 Excel → {(品牌, 商品编码): 文案}。超字数的单元格忽略（会重新生成）。"""
    df = pd.read_excel(path, dtype=str, keep_default_na=False)
    miss = {"品牌", "商品编码"} - set(df.columns)
    if miss:
        raise ValueError(f"❌ {path} 缺少列：{', '.join(miss)}")
    out = {}
    for _, r in df.iterrows():
        key = (r["品牌"].strip().lower(), r["商品编码"].strip())
        vals = {f: r[lab].strip() for f, lab in COPY_LABELS.items() if lab in df.columns}
        for f, v in list(vals.items()):
            if err := check_length(v, f):
                print(f"⚠️ {key[1]} {COPY_LABELS[f]}「{v}」{err}，将重新生成")
                vals[f] = ""
        out[key] = vals
    return out
