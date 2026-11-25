# -*- coding: utf-8 -*-
"""批量生成主图视频：图片目录里的商品 → 取文案 → 渲染（多进程）→ 视频清单 Excel。"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from creative.copywriting.copy_excel import STORE_ID_PREFIX
from creative.copywriting.service import generate_for_brand
from creative.store_items import build_store_items
from creative.video.images import image_dir, scan_images
from creative.video.render import VideoStyle, render_video

CAPTION_FIELDS = ["short_title", "selling_point_1", "selling_point_2", "recommend_reason"]


def _render_one(args):
    images, texts, out, style = args
    render_video(images, texts, out, style)
    return out


def make_videos(brands: list[str], out_dir: Path, codes: list[str] | None = None, style: VideoStyle | None = None,
                copy_mode: str = "safe", use_ai: bool = True, reuse: dict | None = None, limit: int | None = None,
                workers: int = 4, overwrite: bool = False, image_dirs: dict[str, Path] | None = None,
                stores: list[str] | None = None) -> Path | None:
    """
    codes: 只做这些商品编码/渠道产品ID；None = 图片目录里的全部商品。
    reuse: 审核过的文案（copy_excel.read_copy_excel），有则直接用作字幕。
    返回视频清单 Excel 路径。
    """
    style = style or VideoStyle()
    out_dir = Path(out_dir)
    jobs, records = [], []
    for brand in brands:
        brand = brand.lower()
        folder = image_dir(brand, (image_dirs or {}).get(brand))
        if not folder.is_dir():
            print(f"⚠️ [{brand}] 图片目录不存在：{folder}")
            continue
        imgs = scan_images(folder)
        wanted = sorted(imgs) if codes is None else [str(c).strip().upper() for c in codes]
        if codes is None and limit is not None:
            wanted = [c for c in wanted if len(imgs[c]) >= 2][:limit]   # 试跑时只为这几个生成文案
        items = generate_for_brand(brand, codes=wanted, use_ai=use_ai, reuse=reuse, mode=copy_mode)
        found = {p.product_code.upper() for p, _ in items}
        no_db = sorted(c for c in imgs if c in set(wanted) and c not in found)
        if no_db:
            print(f"⚠️ [{brand}] {len(no_db)} 个商品有图片但数据库里没有（无法取文案），跳过：{', '.join(no_db[:8])}")
        n_brand = 0
        for p, r in items:
            pics = imgs.get(p.product_code.upper(), [])
            if len(pics) < 2:
                print(f"⚠️ [{brand}] {p.product_code} 图片不足 2 张，跳过")
                continue
            if limit is not None and n_brand >= limit:
                break
            n_brand += 1
            out = out_dir / brand / f"{p.product_code}.mp4"
            texts = [r.get(f, "") for f in CAPTION_FIELDS]
            records.append((p, r, out, len(pics[:style.max_images])))
            if overwrite or not out.exists():
                jobs.append((pics, texts, out, style))

    if not records:
        print("⚠️ 没有可生成的视频")
        return None
    print(f"🎬 共 {len(records)} 个商品，需渲染 {len(jobs)} 个（已存在的跳过，约 {len(jobs) * 17 / max(workers, 1) / 60:.0f} 分钟）")
    failed = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_render_one, j): j[2] for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                fut.result()
            except Exception as e:
                failed[futs[fut]] = str(e)
                print(f"❌ {futs[fut].name} 失败：{e}")
            if i % 10 == 0 or i == len(jobs):
                print(f"   … {i}/{len(jobs)}")

    store_items = build_store_items([p for p, _, _, _ in records], stores)
    rows = [{
        "品牌": p.brand, "渠道产品ID": p.channel_product_id, "商品编码": p.product_code,
        **{STORE_ID_PREFIX + s.folder: ",".join(s.get(p.product_code)) for s in store_items},
        "视频文件": str(out), "状态": "失败：" + failed[out] if out in failed else ("已生成" if out.exists() else "缺失"),
        "图片数": n, "时长(秒)": style.duration,
        **{k: r.get(f, "") for k, f in zip(["短标题", "卖点1", "卖点2", "推荐理由"], CAPTION_FIELDS)},
    } for p, r, out, n in records]
    path = out_dir / f"视频清单_{'_'.join(brands)}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    ok = sum(r["状态"] == "已生成" for r in rows)
    print(f"✅ 视频 {ok}/{len(rows)} 个可用，清单：{path}")
    return path


def style_with(**kw) -> VideoStyle:
    """在默认样式上改几个参数。"""
    return replace(VideoStyle(), **{k: v for k, v in kw.items() if v is not None})
