"""
图片镜头关键字插入工具（add_shot_keyword）。

将平铺目录中形如 {code}_{n}.ext 的图片，批量重命名为：
  {code}_{keyword}_{n}.ext

常用场景：给换脸/平铺拍摄图加上镜头类型标识（front / flat / detail 等），
使文件名符合 run_ai_face_swap 中 SHOT_SUFFIXES 的约定。

编码提取规则：去掉文件名末尾的 _{数字} 序号后，剩余部分即为编码。
  T839724E_1.webp       → code = T839724E
  T839744F_RED_1.webp   → code = T839744F_RED   （颜色后缀保留）
  T839744F_RED_12.webp  → code = T839744F_RED
  MWX2343BL56_1.jpg     → code = MWX2343BL56
"""
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

# 匹配末尾的 _{整数} 序号，例如 _1 / _12 / _123
_TRAILING_NUM_RE = re.compile(r'^(.+)_(\d+)$')

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def add_shot_keyword(
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
        keyword:    镜头关键字，如 "front" / "flat" / "detail"
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
            m = _TRAILING_NUM_RE.match(p.stem)
            code = m.group(1) if m else p.stem
            groups[code].append(p)

    if not groups:
        print(f"[ADD_SHOT_KW] 未找到任何图片：{input_dir}")
        return []

    total = sum(len(v) for v in groups.values())
    print(f"[ADD_SHOT_KW] {len(groups)} 个编码 / {total} 张图片  keyword={keyword!r}")
    if dry_run:
        print("[ADD_SHOT_KW] >>> DRY RUN，不实际改动 <<<")

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

    print(f"[ADD_SHOT_KW] {'预览' if dry_run else '完成'}：{len(actions)} 张")
    return actions
