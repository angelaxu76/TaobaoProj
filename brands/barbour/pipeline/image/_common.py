# -*- coding: utf-8 -*-
"""图片流水线 step 脚本之间共用的小工具（只依赖轻量库，status.py 也能直接用）。"""
from pathlib import Path

import openpyxl

from ops.ai_image.run_find_unprocessed_faceswap import _build_set

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def list_images(folder, recursive: bool = False) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    it = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def code_of(stem: str) -> str:
    """Barbour 编码本身不含下划线：'MWX0698OL71_front_1_faceswap' -> 'MWX0698OL71'。"""
    return stem.partition("_")[0]


def count_codes(files: list[Path]) -> int:
    return len({code_of(p.stem) for p in files})


def read_codes(path) -> list[str]:
    """读 Excel 第一列编码（第一行为表头）。"""
    path = Path(path)
    if not path.is_file():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    codes = []
    for i, row in enumerate(wb.active.iter_rows(values_only=True)):
        if i == 0:
            continue
        val = row[0] if row else None
        if val is not None and str(val).strip():
            codes.append(str(val).strip())
    wb.close()
    return codes


def write_codes(path, codes: list[str]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["商品编码"])
    for c in codes:
        ws.append([c])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def batch_codes(S, batch_name: str) -> list[str]:
    """本批要换脸的编码：classify/person 里有 SHOT_SUFFIXES 原图的编码，再按批次规则筛选。"""
    batch = S.FACESWAP_BATCHES[batch_name]
    available = sorted({
        code_of(p.stem) for p in list_images(S.PERSON_DIR)
        if any(p.stem.endswith(sfx) for sfx in S.SHOT_SUFFIXES)
    })
    if batch.get("codes_file"):
        wanted = set(read_codes(batch["codes_file"]))
        return [c for c in available if c in wanted]
    prefixes = batch.get("code_prefixes")
    if prefixes:
        return [c for c in available if c.startswith(tuple(prefixes))]
    return available


def missing_shots(S, codes: list[str]) -> dict[str, set[str]]:
    """{code: 还没有换脸结果的后缀集合}，只返回有缺失的编码。

    linkfox_bad 里的图也算已处理：LinkFox 同一张图重换结果一样，不再重新生成。
    """
    if not codes or not Path(S.PERSON_DIR).is_dir():
        return {}
    orig = _build_set(Path(S.PERSON_DIR), S.SHOT_SUFFIXES)
    done: dict[str, set[str]] = {}
    for folder in (Path(S.LINKFOX_DIR), Path(S.LINKFOX_BAD)):
        if folder.is_dir():
            for c, sfx in _build_set(folder, S.SHOT_SUFFIXES, strip_faceswap=True).items():
                done.setdefault(c, set()).update(sfx)
    result = {}
    for c in codes:
        miss = orig.get(c, set()) - done.get(c, set())
        if miss:
            result[c] = miss
    return result


def banner(title: str) -> None:
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


def manual_checkpoint(lines: list[str]) -> None:
    print(f"\n{'#' * 70}\n  [人工检查点]\n{'#' * 70}")
    for line in lines:
        print(f"  {line}")
    print(f"{'#' * 70}\n  随时可运行 status.py 查看当前进度和下一步。\n")
