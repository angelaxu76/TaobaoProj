"""
把同一目录下、按商品编码分组的图片，按优先级重命名为 {code}__1、{code}__2 ...

优先级来源二选一：
  1. brand="barbour" 等 —— 自动从 ops/image_rename/image_priority_config.py 读取该品牌的
     IMAGE_RENAME_PRIORITY（改名专用后缀顺序，与首页/详情页选图逻辑解耦，
     互不影响：改名只决定 {code}__1/__2/... 的物理顺序，首页和详情页各自
     用自己的 IMAGE_FIRST_PRIORITY / IMAGE_DES_PRIORITY 数字索引挑第几张，
     两边可以配成不同的图，不会因为改名而被迫选中同一张）。三个 PRIORITY 键
     完全解耦，各管各的，这里只认 IMAGE_RENAME_PRIORITY，不读 FIRST/DES。
     品牌没配置 IMAGE_RENAME_PRIORITY 会直接报错，不做隐式兜底。
  2. priority_suffixes=(...) —— 显式传入后缀顺序，忽略 cfg。

排序规则：
  1. priority_suffixes 中列出的后缀，按列表顺序取该后缀对应的文件插入
     —— 若某后缀文件不存在则跳过，不占位；每个后缀最多命中一个文件
  2. 其余文件按原文件名字母顺序追加在最后

新文件名用双下划线 "__" 区分于原有的单下划线后缀（如 _8、_front_1_faceswap），
避免和旧文件混淆。也正因如此，重命名后的文件不会再匹配上面的分组规则——
不要对已经跑过一次的目录重复运行，结果不会出错，但也不会有任何效果。

调用方式：
    from ops.image_rename.rename_by_shot_priority import rename_by_shot_priority

    # 方式一：按品牌自动读取 cfg 里的 IMAGE_RENAME_PRIORITY
    rename_by_shot_priority(r"D:\\TB\\Products\\barbour\\repulibcation\\linkfox_processed", brand="barbour")

    # 方式二：显式指定优先级列表，不依赖 cfg
    rename_by_shot_priority(folder, priority_suffixes=("front_pair", "top_left_pair", "m"))
"""
import os
from collections import defaultdict

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _split_code_and_suffix(stem: str) -> tuple[str, str]:
    """'LQU0087BK91_front_1_faceswap' -> ('LQU0087BK91', 'front_1_faceswap')；商品编码本身不含下划线。"""
    code, _, suffix = stem.partition("_")
    return code, suffix


def _resolve_priority_suffixes(brand: str) -> tuple[str, ...]:
    from config import BRAND_CONFIG

    cfg = BRAND_CONFIG.get(brand.lower())
    if cfg is None:
        raise ValueError(f"未找到品牌配置：{brand}")

    priority = cfg.get("IMAGE_RENAME_PRIORITY")
    if not priority:
        raise ValueError(f"{brand} 的 cfg 中未配置 IMAGE_RENAME_PRIORITY")
    return tuple(priority)


def rename_by_shot_priority(
    folder,
    *,
    brand: str | None = None,
    priority_suffixes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> None:
    if priority_suffixes is None:
        if not brand:
            raise ValueError("必须提供 brand（从 cfg 读取 IMAGE_RENAME_PRIORITY）或显式传入 priority_suffixes")
        priority_suffixes = _resolve_priority_suffixes(brand)

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
        by_suffix = dict(groups[code])  # suffix -> filename（同一后缀出现多次时取最后一个）

        ordered: list[str] = []
        used_suffixes: set[str] = set()
        for suffix in priority_suffixes:
            filename = by_suffix.get(suffix)
            if filename is not None:
                ordered.append(filename)
                used_suffixes.add(suffix)

        rest = sorted(fn for suffix, fn in groups[code] if suffix not in used_suffixes)
        ordered.extend(rest)

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


if __name__ == "__main__":
    FOLDER = r"D:\TB\Products\barbour\repulibcation\linkfox_processed"
    BRAND = "barbour"
    DRY_RUN = False  # 先预览确认顺序无误，再改成 False 实际重命名

    rename_by_shot_priority(FOLDER, brand=BRAND, dry_run=DRY_RUN)
