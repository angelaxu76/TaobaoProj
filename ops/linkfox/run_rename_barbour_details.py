"""
将目录下 Barbour 商品图片重命名为 {code}_details.{ext}。

命名规则：
  LCA0416BK11_6.jpg  ->  LCA0416BK11_details.jpg
  编码 = 文件名去掉最后一段 "_<数字>" 后的部分。

同编码多张图片时，仅重命名第一张（按文件名排序），其余跳过不动。
若目标文件 {code}_details.{ext} 已存在，也跳过。

运行：python ops/linkfox/run_rename_barbour_details.py
"""
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, _HERE)

# ============================================================
# 运行参数（按需修改）
# ============================================================

# 图片所在目录
SOURCE_DIR = r"D:\TB\Products\barbour\repulibcation\details"

# 处理的图片扩展名
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 新后缀（不含下划线）
NEW_SUFFIX = "details"

# True = 仅预览不改动；False = 实际执行
DRY_RUN = True

# ============================================================

# 文件名结尾形如 "_6" / "_12"，前面部分作为编码
_SUFFIX_RE = re.compile(r"_\d+$")


def extract_code(filename: str) -> str | None:
    """从文件名（不含扩展名）提取商品编码；不符合 {code}_{数字} 格式则返回 None。"""
    stem = Path(filename).stem
    m = _SUFFIX_RE.search(stem)
    if m:
        return stem[: m.start()]
    return None


def rename_details(source_dir: Path, dry_run: bool = True) -> None:
    if not source_dir.exists():
        print(f"[ERROR] source dir not found: {source_dir}")
        return

    files = sorted(
        f for f in source_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )

    done_codes: set[str] = set()
    renamed = skipped = 0

    for f in files:
        code = extract_code(f.name)
        if not code:
            continue

        if code in done_codes:
            print(f"  SKIP (已处理过该编码): {f.name}")
            skipped += 1
            continue

        target = f.with_name(f"{code}_{NEW_SUFFIX}{f.suffix.lower()}")
        done_codes.add(code)

        if target.exists():
            print(f"  SKIP (目标已存在): {f.name} -> {target.name}")
            skipped += 1
            continue

        if dry_run:
            print(f"  DRY  {f.name} -> {target.name}")
        else:
            f.rename(target)
            print(f"  OK   {f.name} -> {target.name}")
        renamed += 1

    mode = "预览" if dry_run else "执行"
    print(f"\n[{mode}] 完成：重命名 {renamed} 张，跳过 {skipped} 张。")


if __name__ == "__main__":
    rename_details(Path(SOURCE_DIR), dry_run=DRY_RUN)
