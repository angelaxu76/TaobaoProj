"""
图片批量重命名工具。

将平铺目录中的图片按商品编码分组，统一重命名为：
  {code}_{keyword}_{n}.jpg

编码提取规则：文件名第一个下划线之前的部分。
  MWX2343BL56_1.jpg → code = MWX2343BL56
  MWX2343BL56_front_1_faceswap.jpg → code = MWX2343BL56
"""
import os
import shutil
from collections import defaultdict
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def rename_images(
    input_dir: str,
    output_dir: str,
    keyword: str,
    *,
    dry_run: bool = True,
) -> list[tuple[str, str]]:
    """将平铺目录中的图片重命名为 {code}_{keyword}_{n} 格式。

    Args:
        input_dir:  待处理图片目录（平铺结构）
        output_dir: 输出目录（与 input_dir 相同则就地重命名，否则复制到新目录）
        keyword:    重命名关键字，如 "front" / "flat" / "detail"
        dry_run:    True 时只打印预览，不实际操作

    Returns:
        [(old_name, new_name), ...] 所有重命名映射列表
    """
    input_root = Path(input_dir)
    output_root = Path(output_dir)

    if not input_root.is_dir():
        raise NotADirectoryError(f"目录不存在: {input_dir}")

    groups: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(input_root.iterdir()):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            idx = p.stem.find("_")
            code = p.stem[:idx] if idx != -1 else p.stem
            groups[code].append(p)

    if not groups:
        print(f"[RENAME] 未找到任何图片：{input_dir}")
        return []

    total = sum(len(v) for v in groups.values())
    print(f"[RENAME] {len(groups)} 个编码 / {total} 张图片  keyword={keyword!r}")
    if dry_run:
        print("[RENAME] >>> DRY RUN，不实际改动 <<<")

    output_root.mkdir(parents=True, exist_ok=True)
    actions: list[tuple[str, str]] = []

    for code in sorted(groups):
        for n, src in enumerate(sorted(groups[code]), start=1):
            new_name = f"{code}_{keyword}_{n}{src.suffix.lower()}"
            dst = output_root / new_name
            print(f"  {src.name}  →  {new_name}")
            actions.append((src.name, new_name))
            if not dry_run:
                if input_dir == output_dir:
                    src.rename(dst)
                else:
                    shutil.copy2(src, dst)

    print(f"[RENAME] {'预览' if dry_run else '完成'}：{len(actions)} 张")
    return actions
