"""
AI 人物/非人物图片自动分类脚本。

使用 YOLOv8 检测图片中是否含有人物，将图片分发到两个输出目录：
  - 人物图（模特拍摄）→ PERSON_DIR
  - 非人物图（细节/平铺）→ DETAIL_DIR

依赖：pip install ultralytics
首次运行会自动下载模型文件（yolov8n.pt，约 6 MB）。

运行：python ops/run_classify_person_images.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
from pathlib import Path

# ============================================================
# 运行参数（按需修改）
# ============================================================

# 待扫描的图片目录（支持平铺结构 或 按编码的子目录结构）
INPUT_DIR = r"D:\TB\Products\barbour\repulibcation\need_edit"

# 包含人物（模特）的图片输出目录
PERSON_DIR = r"D:\TB\Products\barbour\repulibcation\classify\person"

# 非人物图片（产品细节/平铺图）输出目录
DETAIL_DIR = r"D:\TB\Products\barbour\repulibcation\classify\detail"

# 是否递归扫描子目录
#   True  — 扫描所有子目录（按编码子目录结构时使用）
#   False — 只扫描顶层文件（平铺目录时使用）
RECURSIVE = True

# 人物检测置信度阈值（0~1，越高越严格；推荐 0.35~0.45）
CONFIDENCE = 0.4

# 支持的图片格式
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================


def _collect_images(input_dir: str, recursive: bool) -> list[Path]:
    root = Path(input_dir)
    pattern = root.rglob("*") if recursive else root.iterdir()
    return sorted(p for p in pattern if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def _safe_copy(src: Path, dst_dir: str, input_root: Path) -> str:
    """复制图片到目标目录，同名时用父目录名做前缀避免覆盖。"""
    dst = Path(dst_dir) / src.name
    if dst.exists():
        dst = Path(dst_dir) / f"{src.parent.name}_{src.name}"
    shutil.copy2(src, dst)
    return str(src.relative_to(input_root))


def classify_images(
    input_dir: str,
    person_dir: str,
    detail_dir: str,
    *,
    recursive: bool = True,
    confidence: float = 0.4,
) -> None:
    from ultralytics import YOLO

    input_root = Path(input_dir)
    if not input_root.is_dir():
        raise NotADirectoryError(f"INPUT_DIR 不存在: {input_dir}")

    os.makedirs(person_dir, exist_ok=True)
    os.makedirs(detail_dir, exist_ok=True)

    images = _collect_images(input_dir, recursive)
    if not images:
        print(f"未找到任何图片：{input_dir}")
        return

    print(f"共找到 {len(images)} 张图片，加载模型中...")
    # classes=[0] 只检测 person 类，跳过其他类加速推理
    model = YOLO("yolov8n.pt")

    person_count = 0
    detail_count = 0
    fail_count = 0

    for img_path in images:
        try:
            results = model(str(img_path), conf=confidence, classes=[0], verbose=False)
            has_person = any(len(r.boxes) > 0 for r in results)

            dst_dir = person_dir if has_person else detail_dir
            rel = _safe_copy(img_path, dst_dir, input_root)

            label = "PERSON" if has_person else "DETAIL"
            print(f"[{label}] {rel}")

            if has_person:
                person_count += 1
            else:
                detail_count += 1

        except Exception as e:
            print(f"[ERROR] {img_path.name}: {e}")
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"完成 | 人物={person_count}  细节={detail_count}  失败={fail_count}")
    print(f"人物图 → {person_dir}")
    print(f"细节图 → {detail_dir}")


def main():
    classify_images(
        input_dir=INPUT_DIR,
        person_dir=PERSON_DIR,
        detail_dir=DETAIL_DIR,
        recursive=RECURSIVE,
        confidence=CONFIDENCE,
    )


if __name__ == "__main__":
    main()
