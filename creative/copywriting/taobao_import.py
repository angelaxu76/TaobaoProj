# -*- coding: utf-8 -*-
"""
淘宝「商品素材导入模板-[淘宝]基础素材」：按店铺各生成一个导入文件。

商品ID 是各店自己的淘宝商品ID（映射见 creative/store_items.py），所以每店一个文件，一个商品ID 一行。
只填文案列，图片列（白底图/透明图/方版场景图/长图）留空。
模板更新时替换同目录的 taobao_import_template.xlsx 即可，按表头名称填列。
"""
from __future__ import annotations

import warnings
from pathlib import Path

import openpyxl

from creative.copywriting.validator import mentions_color
from creative.product_source import ProductInfo
from creative.store_items import StoreItems

TEMPLATE = Path(__file__).with_name("taobao_import_template.xlsx")
ID_HEADER = "商品ID(必填)"
HEADER_FIELDS = {
    "卖点1": "selling_point_1",
    "卖点2": "selling_point_2",
    "短标题": "short_title",
    "宝贝名称": "item_name",
    "宝贝推荐理由": "recommend_reason",
}


def _pick_rows(items: list[tuple[ProductInfo, dict]], store: StoreItems) -> dict[str, dict]:
    """淘宝商品ID → 文案。一个宝贝含多个颜色时，优先用没提颜色的文案，其次商家编码直接对上的那个。"""
    candidates: dict[str, list[tuple]] = {}
    for n, (p, r) in enumerate(items):
        how = store.match.get(p.product_code.upper(), 0)
        color = any(mentions_color(r.get(f)) for f in HEADER_FIELDS.values())
        for item_id in store.get(p.product_code):
            candidates.setdefault(item_id, []).append((color, how, n, r))
    return {item_id: min(c, key=lambda x: x[:3])[3] for item_id, c in candidates.items()}


def write_taobao_import(items: list[tuple[ProductInfo, dict]], store_items: list[StoreItems],
                        out_dir: Path, tag: str) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for store in store_items:
        rows = _pick_rows(items, store)
        no_id = [p.product_code for p, _ in items if not store.get(p.product_code)]
        if rows:
            path = out_dir / f"淘宝素材导入_{store.folder}_{tag}.xlsx"
            _write(rows, path)
            paths.append(path)
            print(f"✅ [{store.folder}] 导入文件 {len(rows)} 行：{path}")
        else:
            print(f"⚠️ [{store.folder}] 没有可导入的商品")
        if no_id:
            print(f"   ⚠️ {len(no_id)} 个商品在该店找不到淘宝商品ID，未写入：{', '.join(no_id[:8])}"
                  f"{' …' if len(no_id) > 8 else ''}（审核 Excel 里该店 ID 列为空）")
    return paths


def _write(rows: dict[str, dict], path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # 模板无默认样式的提示
        wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb.active
    cols = {str(c.value).strip(): c.column for c in ws[1] if c.value}
    missing = {ID_HEADER, *HEADER_FIELDS} - set(cols)
    if missing:
        raise ValueError(f"❌ 模板缺少列：{', '.join(sorted(missing))}")
    for i, (item_id, r) in enumerate(rows.items(), start=2):
        ws.cell(i, cols[ID_HEADER], item_id).number_format = "@"   # 文本，避免科学计数法
        for header, f in HEADER_FIELDS.items():
            ws.cell(i, cols[header], r.get(f) or None)
    wb.save(path)
