# -*- coding: utf-8 -*-
"""批量生成主图视频：图片目录里的商品 → 取文案 → 渲染（多进程）→ 视频清单 Excel。"""
from __future__ import annotations

import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import BRAND_CONFIG

from creative.copywriting.copy_excel import STORE_ID_PREFIX
from creative.copywriting.service import generate_for_brand
from creative.store_items import build_store_items
from creative.video.images import image_dir, scan_images
from creative.video.render import VideoStyle, list_music, media_duration, render_video

CAPTION_FIELDS = ["short_title", "selling_point_1", "selling_point_2", "recommend_reason"]


def _render_one(args):
    images, texts, out, style = args
    render_video(images, texts, out, style)
    return out


class MusicPicker:
    """style.music 为文件夹时，每个商品挑一首、并在前 MAX_START 秒内挑一个起播点。
    按商品编码固定（不是每次运行都变），所以重做同一商品时背景音乐不变；音乐文件夹增删文件后会重新分配。"""
    MAX_START = 20.0

    def __init__(self, spec, duration: float):
        self.files = list_music(spec)
        self.duration = duration
        self._len: dict[Path, float] = {}

    def pick(self, code: str) -> tuple[str | None, float]:
        if not self.files:
            return None, 0.0
        h = int(hashlib.md5(code.upper().encode()).hexdigest(), 16)
        f = self.files[h % len(self.files)]
        if f not in self._len:
            self._len[f] = media_duration(f)
        room = min(self.MAX_START, self._len[f] - self.duration - 1)
        start = (h // len(self.files) % 1000) / 1000 * room if room > 0 else 0.0
        return str(f), round(start, 1)


def video_dir(brand: str, root: Path | None = None) -> Path:
    """视频输出目录：默认 {品牌 BASE}\\document\\video（流水线清理只清 publication / repulibcation，不会删）。
    品牌配置里可用 VIDEO_DIR 单独指定；root 不为空时改为 {root}\\{品牌}（测试用）。"""
    if root is not None:
        return Path(root) / brand
    cfg = BRAND_CONFIG[brand]
    return Path(cfg.get("VIDEO_DIR", Path(cfg["BASE"]) / "document" / "video"))


def make_videos(brands: list[str], out_root: Path | None = None, codes: list[str] | None = None,
                style: VideoStyle | None = None, copy_mode: str = "safe", use_ai: bool = True,
                reuse: dict | None = None, limit: int | None = None, workers: int = 4, overwrite: bool = False,
                image_dirs: dict[str, Path] | None = None, stores: list[str] | None = None) -> list[Path]:
    """
    视频和清单都放各品牌自己的目录（见 video_dir）。
    codes: 只做这些商品编码/渠道产品ID；None = 图片目录里的全部商品。
    reuse: 审核过的文案（copy_excel.read_copy_excel），有则直接用作字幕。
    返回各品牌视频清单 Excel 路径。
    """
    style = style or VideoStyle()
    music = MusicPicker(style.music, style.duration)
    if music.files:
        print(f"🎵 背景音乐 {len(music.files)} 首，按商品编码分配")
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
        matched = found | {p.channel_product_id.upper() for p, _ in items}   # codes 里也可能是渠道产品ID
        unmatched = sorted(set(wanted) - matched)
        if unmatched:
            print(f"⚠️ [{brand}] {len(unmatched)} 个编码在数据库里找不到（无法取文案），跳过：{', '.join(unmatched[:8])}"
                  f"{' …' if len(unmatched) > 8 else ''}")
        n_brand = 0
        for p, r in items:
            pics = imgs.get(p.product_code.upper(), [])
            if len(pics) < 2:
                print(f"⚠️ [{brand}] {p.product_code} 图片不足 2 张，跳过")
                continue
            if limit is not None and n_brand >= limit:
                break
            n_brand += 1
            out = video_dir(brand, out_root) / f"{p.product_code}_video.mp4"
            texts = [r.get(f, "") for f in CAPTION_FIELDS]
            track, start = music.pick(p.product_code)
            p_style = replace(style, music=track, music_start=start)
            records.append((p, r, out, len(pics[:style.max_images]), track, start))
            if overwrite or not out.exists():
                jobs.append((pics, texts, out, p_style))

    if not records:
        print("⚠️ 没有可生成的视频")
        return []
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

    store_items = build_store_items([p for p, *_ in records], stores)
    rows = [{
        "品牌": p.brand, "渠道产品ID": p.channel_product_id, "商品编码": p.product_code,
        **{STORE_ID_PREFIX + s.folder: ",".join(s.get(p.product_code)) for s in store_items},
        "视频文件": str(out), "状态": "失败：" + failed[out] if out in failed else ("已生成" if out.exists() else "缺失"),
        "图片数": n, "时长(秒)": style.duration,
        "背景音乐": Path(track).name if track else "（静音）", "音乐起点(秒)": start if track else "",
        **{k: r.get(f, "") for k, f in zip(["短标题", "卖点1", "卖点2", "推荐理由"], CAPTION_FIELDS)},
    } for p, r, out, n, track, start in records]
    paths = []
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    for brand, df in pd.DataFrame(rows).groupby("品牌", sort=False):   # 每个品牌一份清单，放在该品牌视频目录
        path = video_dir(brand, out_root) / f"视频清单_{brand}_{stamp}.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(path, index=False)
        paths.append(path)
        print(f"✅ [{brand}] 视频 {(df['状态'] == '已生成').sum()}/{len(df)} 个可用，目录：{path.parent}")
    return paths


def style_with(**kw) -> VideoStyle:
    """在默认样式上改几个参数。"""
    return replace(VideoStyle(), **{k: v for k, v in kw.items() if v is not None})
