# move_non_barbour_files.py
import re
import shutil
from pathlib import Path


# Barbour 编码文件名规则：MTS1296BL45.txt / LQU1800NY51.txt ...
BARBOUR_TXT_RE = re.compile(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2}\.txt$", re.IGNORECASE)


def move_non_barbour_files(input_dir: str, bad_dir: str) -> dict:
    """
    将 input_dir 下 “非 Barbour 编码格式” 的文件移动到 bad_dir

    参数:
      input_dir: 输入目录，例如 D:\\TB\\Products\\barbour\\publication\\terraces\\TXT
      bad_dir:   非编码文件移动到的目录，例如 D:\\TB\\Products\\barbour\\publication\\terraces\\TXT_BAD

    返回:
      统计信息 dict
    """
    src = Path(input_dir)
    dst = Path(bad_dir)

    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Input dir not found: {src}")

    dst.mkdir(parents=True, exist_ok=True)

    moved = 0
    kept = 0
    skipped = 0
    errors = 0

    for p in src.iterdir():
        # 只处理文件
        if not p.is_file():
            skipped += 1
            continue

        name = p.name

        # 符合 Barbour 编码格式的 txt 文件：保留
        if BARBOUR_TXT_RE.match(name):
            kept += 1
            continue

        # 其他任何文件（比如 .done_urls.txt / NoCode_*.txt / 乱名文件）：移动
        target = dst / name

        # 如果目标已存在，避免覆盖：自动改名追加 _dupN
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            i = 1
            while True:
                alt = dst / f"{stem}_dup{i}{suffix}"
                if not alt.exists():
                    target = alt
                    break
                i += 1

        try:
            shutil.move(str(p), str(target))
            moved += 1
        except Exception as e:
            errors += 1
            print(f"[ERROR] move failed: {p} -> {target} | {e}")

    summary = {
        "input_dir": str(src),
        "bad_dir": str(dst),
        "kept_barbour_txt": kept,
        "moved_non_barbour": moved,
        "skipped_non_files": skipped,
        "errors": errors,
    }
    return summary


if __name__ == "__main__":
    # 直接运行时的示例（你可以按需改路径）
    input_dir = r"D:\TB\Products\barbour\publication\terraces\TXT"
    bad_dir = r"D:\TB\Products\barbour\publication\terraces\TXT_NON_BARBOUR"

    result = move_non_barbour_files(input_dir, bad_dir)
    print("\n=== Summary ===")
    for k, v in result.items():
        print(f"{k}: {v}")
