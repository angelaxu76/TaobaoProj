"""
AI 人物/非人物图片自动分类。

使用 YOLOv8 检测图片中是否含有人物（可选：要求必须有头部），将图片分发到两个输出目录：
  - 人物图（模特拍摄，含头部）→ person_dir
  - 非人物图（细节/平铺/仅手部）→ detail_dir

依赖：pip install ultralytics
首次运行会自动下载模型文件（约 6 MB）。

调用方式：
    from helper.image.classify_person_images import classify_images

    # 默认：有头部才算人物图（推荐，适合服装电商）
    classify_images(
        input_dir=r"D:\\TB\\Products\\marksandspencer\\image_download",
        person_dir=r"D:\\TB\\Products\\marksandspencer\\classify\\person",
        detail_dir=r"D:\\TB\\Products\\marksandspencer\\classify\\detail",
        recursive=True,
        require_head=True,   # True = 必须检测到头部关键点
        confidence=0.4,
        head_confidence=0.3, # 头部关键点置信度阈值
    )
"""
import os
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# YOLOv8 Pose 模型关键点索引（COCO 17点）
# 0=鼻, 1=左眼, 2=右眼, 3=左耳, 4=右耳
_HEAD_KEYPOINT_INDICES = [0, 1, 2, 3, 4]


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


def _has_head_keypoints(results, head_confidence: float) -> bool:
    """判断姿态估计结果中是否有头部关键点置信度足够高的人物。"""
    for r in results:
        if r.keypoints is None:
            continue
        # r.keypoints.conf: shape (num_persons, 17)
        confs = r.keypoints.conf
        if confs is None:
            continue
        for person_conf in confs:
            # 检查鼻/眼/耳任意一个关键点置信度超过阈值
            for idx in _HEAD_KEYPOINT_INDICES:
                if float(person_conf[idx]) >= head_confidence:
                    return True
    return False


def classify_images(
    input_dir: str,
    person_dir: str,
    detail_dir: str,
    *,
    recursive: bool = True,
    require_head: bool = True,
    confidence: float = 0.4,
    head_confidence: float = 0.3,
) -> None:
    """
    扫描 input_dir，将含人物的图片复制到 person_dir，其余复制到 detail_dir。

    Args:
        input_dir:       待扫描的图片目录
        person_dir:      含人物（模特）的图片输出目录
        detail_dir:      非人物图片（细节/平铺/仅手部）输出目录
        recursive:       是否递归扫描子目录
        require_head:    True = 必须检测到头部关键点才算人物图（推荐）
                         False = 任意人体部位均算人物图（原始行为）
        confidence:      人物检测置信度阈值（0~1，推荐 0.35~0.45）
        head_confidence: 头部关键点置信度阈值，仅 require_head=True 时生效（推荐 0.25~0.35）
    """
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

    if require_head:
        model_name = "yolov8n-pose.pt"  # 姿态估计，检测头部关键点
        print(f"模式：require_head=True（使用姿态估计模型 {model_name}）")
    else:
        model_name = "yolov8n.pt"       # 通用目标检测
        print(f"模式：require_head=False（使用目标检测模型 {model_name}）")

    print(f"共找到 {len(images)} 张图片，加载模型中...")
    model = YOLO(model_name)  # 首次运行自动下载

    person_count = detail_count = fail_count = 0

    for img_path in images:
        try:
            results = model(str(img_path), conf=confidence, classes=[0], verbose=False)

            if require_head:
                has_person = _has_head_keypoints(results, head_confidence)
            else:
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
