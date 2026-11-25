# -*- coding: utf-8 -*-
"""商品图片查找：{商品编码}__{序号}.jpg（也兼容 {编码}_{序号}、{编码}-{序号}），按序号排序。"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from config import BRAND_CONFIG

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_NAME_RE = re.compile(r"^(?P<code>.+?)(?:__|_|-)(?P<idx>\d{1,2})$")


def image_dir(brand: str, override: Path | None = None) -> Path:
    return Path(override or BRAND_CONFIG[brand.lower()]["IMAGE_PROCESS"])


def scan_images(folder: Path) -> dict[str, list[Path]]:
    """商品编码（大写）→ 按序号排好的图片列表。"""
    found: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for f in Path(folder).iterdir():
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        m = _NAME_RE.match(f.stem)
        if m:
            found[m.group("code").upper()].append((int(m.group("idx")), f))
    return {code: [f for _, f in sorted(items)] for code, items in found.items()}
