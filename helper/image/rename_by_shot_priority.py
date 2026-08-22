"""
把同一目录下、按商品编码分组的图片，按固定优先级重命名为 {code}__1、{code}__2 ...

排序规则：
  1. {code}_front_{n}_faceswap.*  按 n 从小到大排列
  2. priority_suffixes 中列出的后缀（默认只有 "6"），按列表顺序插入
     —— 若某后缀文件不存在则跳过，不占位
  3. 其余文件按原文件名字母顺序追加在最后

新文件名用双下划线 "__" 区分于原有的单下划线后缀（如 _3、_5、_front_1_faceswap），
避免和旧文件混淆。也正因如此，重命名后的文件不会再匹配上面的分组规则——
不要对已经跑过一次的目录重复运行，结果不会出错，但也不会有任何效果。

调用方式：
    from helper.image.rename_by_shot_priority import rename_by_shot_priority

    rename_by_shot_priority(r"D:\\TB\\Products\\barbour\\repulibcation\\linkfox_processed")
"""
import os
import re
from collections import defaultdict

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

_FRONT_FACESWAP_RE = re.compile(r"^front_(\d+)_faceswap$", re.IGNORECASE)


def _split_code_and_suffix(stem: str) -> tuple[str, str]:
    """'LQU0087BK91_front_1_faceswap' -> ('LQU0087BK91', 'front_1_faceswap')；商品编码本身不含下划线。"""
    code, _, suffix = stem.partition("_")
    return code, suffix


def rename_by_shot_priority(
    folder,
    *,
    priority_suffixes: tuple[str, ...] = ("6",),
    dry_run: bool = False,
) -> None:
    folder = str(folder)
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)  # code -> [(suffix, filename)]

    for filename in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in IMAGE_EXTS:
            continue
        code, suffix = _split_code_and_suffix(stem)
        if not suffix:
            continue
        groups[code].append((suffix, filename))

    total_renamed = 0
    for code in sorted(groups):
        faceswap: list[tuple[int, str]] = []
        priority_hit: dict[str, str] = {}
        rest: list[str] = []

        for suffix, filename in groups[code]:
            m = _FRONT_FACESWAP_RE.match(suffix)
            if m:
                faceswap.append((int(m.group(1)), filename))
            elif suffix in priority_suffixes:
                priority_hit[suffix] = filename
            else:
                rest.append(filename)

        faceswap.sort(key=lambda t: t[0])
        ordered = [fn for _, fn in faceswap]
        for s in priority_suffixes:
            if s in priority_hit:
                ordered.append(priority_hit[s])
        ordered.extend(sorted(rest))

        for i, filename in enumerate(ordered, start=1):
            _, ext = os.path.splitext(filename)
            new_name = f"{code}__{i}{ext}"
            if filename == new_name:
                continue

            src = os.path.join(folder, filename)
            dst = os.path.join(folder, new_name)
            if os.path.exists(dst):
                print(f"[SKIP] 目标文件已存在，跳过改名: {dst}")
                continue

            if dry_run:
                print(f"[DRY] {filename} -> {new_name}")
            else:
                os.rename(src, dst)
                print(f"[OK] {filename} -> {new_name}")
            total_renamed += 1

    print(f"\n完成，共处理 {len(groups)} 个商品编码，{'预计' if dry_run else '实际'}重命名 {total_renamed} 个文件。")
