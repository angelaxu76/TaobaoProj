# -*- coding: utf-8 -*-
"""
TOAST 商品图片 + 视频下载

- 图片来自 /products/{handle}.js 的 images（Shopify CDN 原图，按站点展示顺序）
- 保存为 IMAGE_DOWNLOAD/{商品编码}_{序号}.jpg，序号从 1 开始（1 通常是平铺/正面图，后面是模特图，最后是背面）
- 视频来自 media 里 media_type == "video" 的条目，取最高分辨率 mp4（一般 1080p，约 10 秒）
  保存为 VIDEO_DOWNLOAD/{商品编码}_{序号}.mp4；只有部分商品有视频。download_videos=False 可关闭
- 两种入口：
    download_toast_images()                 按 LINKS_FILE 下载全部
    download_images_from_codes(codes_file)  按编码清单下载（编码 → TXT 里的 Source URL）
"""
from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from config import TOAST
from brands.toast.shopify_api import HEADERS, derive_product_code, fetch_product_js, image_urls, video_urls

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

IMAGE_DIR = Path(TOAST["IMAGE_DOWNLOAD"])
VIDEO_DIR = Path(TOAST["VIDEO_DOWNLOAD"])
TXT_DIR = Path(TOAST["TXT_DIR"])


def _download_file(file_url: str, save_path: Path, max_retries: int = 3, timeout: int = 30) -> bool:
    if save_path.exists() and save_path.stat().st_size > 0:
        return True
    tmp = save_path.with_suffix(save_path.suffix + ".part")
    for attempt in range(1, max_retries + 1):
        try:
            with requests.get(file_url, headers=HEADERS, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1024 * 256):
                        if chunk:
                            f.write(chunk)
            os.replace(tmp, save_path)
            return True
        except Exception as e:
            if attempt == max_retries:
                print(f"❌ 下载失败: {save_path.name} ← {file_url}: {e}")
                tmp.unlink(missing_ok=True)
                return False
            time.sleep(attempt)
    return False


def download_product(
    url: str, idx: int = 0, code: Optional[str] = None, download_videos: bool = True
) -> Tuple[str, int, int]:
    """下载单个商品全部图片（和视频），返回 (编码, 成功数, 总数)，数量含视频"""
    product = fetch_product_js(url)
    code = code or derive_product_code(product)

    imgs = image_urls(product)
    img_ok = 0
    for n, img_url in enumerate(imgs, 1):
        ext = os.path.splitext(img_url)[1].lower() or ".jpg"
        if _download_file(img_url, IMAGE_DIR / f"{code}_{n}{ext}"):
            img_ok += 1

    vids = video_urls(product) if download_videos else []
    vid_ok = 0
    for n, vid_url in enumerate(vids, 1):
        if _download_file(vid_url, VIDEO_DIR / f"{code}_{n}.mp4", timeout=120):
            vid_ok += 1

    msg = f"✅ {idx:04d} {code}: 图片 {img_ok}/{len(imgs)}"
    if vids:
        msg += f"，视频 {vid_ok}/{len(vids)}"
    print(msg)
    return code, img_ok + vid_ok, len(imgs) + len(vids)


def _run(tasks: List[Tuple[str, Optional[str]]], max_workers: int, download_videos: bool = True) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    if download_videos:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    failed: List[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(download_product, url, i, code, download_videos): url
            for i, (url, code) in enumerate(tasks, 1)
        }
        for fut in as_completed(futs):
            try:
                _, ok, total = fut.result()
                if total == 0 or ok < total:
                    failed.append(futs[fut])
            except Exception as e:
                print(f"💥 {futs[fut]}: {e}")
                failed.append(futs[fut])
    n_videos = len(list(VIDEO_DIR.glob("*.mp4"))) if download_videos and VIDEO_DIR.exists() else 0
    print(f"🎯 下载完成：{len(tasks) - len(failed)}/{len(tasks)} 个商品完整")
    print(f"   图片目录：{IMAGE_DIR}")
    if download_videos:
        print(f"   视频目录：{VIDEO_DIR}（共 {n_videos} 个视频）")
    if failed:
        print("⚠️ 未完整下载：", failed[:10])


def download_toast_images(
    links_file: Optional[Path] = None, max_workers: int = 6, download_videos: bool = True
) -> None:
    links_file = Path(links_file or TOAST["LINKS_FILE"])
    with open(links_file, "r", encoding="utf-8") as f:
        urls = list(dict.fromkeys(u.strip() for u in f if u.strip()))
    print(f"📦 共 {len(urls)} 个商品，开始下载图片{'和视频' if download_videos else ''}...")
    _run([(u, None) for u in urls], max_workers, download_videos)


def _url_from_txt(code: str) -> Optional[str]:
    txt = TXT_DIR / f"{code}.txt"
    if not txt.exists():
        return None
    with open(txt, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("Source URL:"):
                return line.split(":", 1)[1].strip()
    return None


def download_images_from_codes(
    codes_file: str | Path, max_workers: int = 6, download_videos: bool = True
) -> None:
    with open(codes_file, "r", encoding="utf-8") as f:
        codes = list(dict.fromkeys(re.sub(r"\s+", "", c).upper() for c in f if c.strip()))

    tasks: List[Tuple[str, Optional[str]]] = []
    for code in codes:
        url = _url_from_txt(code)
        if url:
            tasks.append((url, code))
        else:
            print(f"⚠️ 找不到 TXT / Source URL，跳过：{code}")
    print(f"📦 编码 {len(codes)} 个，可下载 {len(tasks)} 个，开始下载图片{'和视频' if download_videos else ''}...")
    _run(tasks, max_workers, download_videos)


if __name__ == "__main__":
    # 默认按 product_links.txt 下载全部
    download_toast_images()

    # 只下载指定编码时，改用：
    # download_images_from_codes(r"D:\TB\Products\toast\repulibcation\publication_codes.txt")
