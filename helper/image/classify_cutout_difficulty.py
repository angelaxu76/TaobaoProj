"""
按前景（非背景）像素占比自动分类图片，挑出背景/留白过少、容易被抠图算法
（如 rembg）错误抠取边缘的图片。

判定逻辑：
    用四角像素的平均色作为该图的背景色采样，计算每个像素与背景色的差异，
    统计与背景色差异较大的像素（前景像素）占全图比例 fg_ratio。
    fg_ratio 越高，说明画面里留白/背景越少（例如面料特写、拉满整个画幅的图），
    这类图抠图时容易连主体边缘一起被误判为背景或反之。
    fg_ratio >= threshold 判定为"难抠图"，移动/复制到 hard_dir；其余保留在原目录。

阈值来源：对 D:\\TB\\Products\\barbour\\images\\detail（人工判定为正常）与
repulibcation\\1（人工判定为难抠图）两批已分类样本做了统计，threshold=0.65 时
准确率约 91%。这是像素级启发式方法，无法保证 100% 准确，输出中会额外列出
ratio 落在阈值 ±BORDERLINE_MARGIN 内的边界图片，建议人工复核。

调用方式：
    from helper.image.classify_cutout_difficulty import split_hard_to_cut

    split_hard_to_cut(
        input_dir=r"D:\\TB\\Products\\barbour\\images\\detail",
        hard_dir=r"D:\\TB\\Products\\barbour\\repulibcation\\1",
    )
"""
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

DEFAULT_THRESHOLD = 0.65
DIFF_TOL = 30              # 单像素与背景色差异之和超过该值才算前景像素
BORDERLINE_MARGIN = 0.03   # ratio 落在 threshold ± margin 内时提示人工复核


def _foreground_ratio(path: Path) -> float:
    img = Image.open(path).convert("RGB")
    arr = np.array(img)
    corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]], dtype=float)
    bg_color = tuple(int(c) for c in corners.mean(axis=0))
    bg = Image.new("RGB", img.size, bg_color)
    diff = np.array(ImageChops.difference(img, bg)).astype(int).sum(axis=2)
    mask = diff > DIFF_TOL
    return float(mask.mean())


def split_hard_to_cut(
    input_dir: str,
    hard_dir: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    move: bool = True,
    dry_run: bool = False,
) -> None:
    """
    扫描 input_dir 下的图片，把前景占比 >= threshold 的图片移动/复制到 hard_dir，
    其余保留在 input_dir 原地不动。

    Args:
        input_dir: 待分类图片所在目录（不递归子目录）
        hard_dir:  难抠图图片的目标目录
        threshold: 前景占比阈值，越高越严格（默认 0.65，来自样本统计）
        move:      True=移动（默认，原目录不再保留难抠图副本）；False=复制
        dry_run:   True=只打印分类结果，不实际移动/复制文件
    """
    src_root = Path(input_dir)
    if not src_root.is_dir():
        raise NotADirectoryError(f"INPUT_DIR 不存在: {input_dir}")

    dst_root = Path(hard_dir)
    if not dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)

    images = sorted(p for p in src_root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"未找到任何图片：{input_dir}")
        return

    easy_count = hard_count = fail_count = 0
    borderline: list[tuple[float, str]] = []

    for img_path in images:
        try:
            ratio = _foreground_ratio(img_path)
        except Exception as e:
            print(f"[ERROR] {img_path.name}: {e}")
            fail_count += 1
            continue

        is_hard = ratio >= threshold
        if abs(ratio - threshold) <= BORDERLINE_MARGIN:
            borderline.append((ratio, img_path.name))

        label = "HARD" if is_hard else "EASY"
        print(f"[{label}] ratio={ratio:.3f}  {img_path.name}")

        if is_hard:
            hard_count += 1
            if not dry_run:
                dst = dst_root / img_path.name
                if dst.exists():
                    dst = dst_root / f"{img_path.stem}_dup{img_path.suffix}"
                if move:
                    shutil.move(str(img_path), dst)
                else:
                    shutil.copy2(img_path, dst)
        else:
            easy_count += 1

    print(f"\n{'=' * 60}")
    print(f"完成 | 正常(留在原地)={easy_count}  难抠图(已{'移动' if move else '复制'})={hard_count}  失败={fail_count}")
    print(f"难抠图 → {hard_dir}")
    if borderline:
        print(f"\n以下 {len(borderline)} 张图 ratio 接近阈值({threshold})，启发式判断不够可靠，建议人工复核：")
        for ratio, name in sorted(borderline):
            print(f"  {ratio:.3f}  {name}")
