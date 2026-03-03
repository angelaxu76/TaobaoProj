"""
换脸图头身比例检测脚本。

原理：
  - YOLOv8-pose 检测左右肩膀关键点 → 计算肩宽
  - OpenCV Haar cascade 检测人脸矩形 → 计算头宽
  - 头宽 / 肩宽 = 头肩比
      正常时装摄影：0.38 ~ 0.58
      换脸图脸太大：> 0.65（主要问题）
      头太小（极少）：< 0.30
  - 比例超出阈值的图片移动到 BAD_DIR

输出：
  BAD_DIR       超出比例阈值的图片
  REPORT_CSV    每张图的头肩比 + 判定结果

用法：
  1. 修改下方运行参数。
  2. python ops/ai_image/run_check_head_proportion.py

依赖：pip install ultralytics opencv-python（已有则无需重装）
首次运行自动下载 yolov8n-pose.pt（约 6 MB）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import csv
import shutil
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np

# ============================================================
# 运行参数（按需修改）
# ============================================================

# 待检测的图片目录（换脸输出目录）
INPUT_DIR  = r"D:\barbour\images\ai_gen\faceswap_output"

# 比例不合格的图片移动到这里
BAD_DIR    = r"D:\barbour\images\ai_gen\faceswap_bad_proportion"

# 报告 CSV 路径
REPORT_CSV = r"D:\barbour\images\ai_gen\proportion_report.csv"

# 头肩比阈值：超出此范围则判定为 BAD
# 正常范围 0.38~0.58；换脸图脸太大通常 > 0.65
RATIO_MIN = 0.30   # 低于此值：头太小（极少见）
RATIO_MAX = 0.65   # 高于此值：脸太大（换脸主要问题）

# 低质量图片：True=移动（原文件消失），False=复制（原文件保留）
MOVE_BAD_FILES = True

# 是否递归扫描子目录
RECURSIVE = False

# 支持的图片格式
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================

# YOLOv8-pose 关键点索引（COCO 格式）
_KP_LEFT_SHOULDER  = 5
_KP_RIGHT_SHOULDER = 6
_KP_LEFT_HIP       = 11
_KP_RIGHT_HIP      = 12

# 肩膀关键点置信度阈值（低于此值的点视为未检测到）
_KP_CONF_THRESHOLD = 0.3

_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def _load_pose_model():
    from ultralytics import YOLO
    return YOLO("yolov8n-pose.pt")


def _detect_face(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """返回面积最大的人脸 (x, y, w, h)，未检测到返回 None。"""
    faces = _face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def _detect_shoulders(model, img_bgr: np.ndarray) -> tuple[float, float] | None:
    """
    用 YOLOv8-pose 检测肩膀关键点。
    返回 (shoulder_width_px, img_width)，未检测到返回 None。
    """
    results = model(img_bgr, verbose=False)
    if not results:
        return None

    # 选置信度最高的 person
    best_kps = None
    best_conf = -1.0
    for r in results:
        if r.keypoints is None or r.keypoints.data is None:
            continue
        for person_kps in r.keypoints.data:
            # person_kps: shape (17, 3) — x, y, conf
            if person_kps.shape[0] < 13:
                continue
            ls = person_kps[_KP_LEFT_SHOULDER]
            rs = person_kps[_KP_RIGHT_SHOULDER]
            conf = float(ls[2] + rs[2]) / 2
            if conf > best_conf:
                best_conf = conf
                best_kps = person_kps

    if best_kps is None or best_conf < _KP_CONF_THRESHOLD:
        return None

    ls = best_kps[_KP_LEFT_SHOULDER]
    rs = best_kps[_KP_RIGHT_SHOULDER]
    if float(ls[2]) < _KP_CONF_THRESHOLD or float(rs[2]) < _KP_CONF_THRESHOLD:
        return None

    shoulder_width = abs(float(ls[0]) - float(rs[0]))
    return shoulder_width, float(img_bgr.shape[1])


def analyze_proportion(model, image_path: Path) -> dict:
    """
    分析单张图片的头肩比。
    返回含 ratio / verdict / error 等字段的 dict。
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return {"ratio": None, "verdict": "ERROR", "error": "无法读取图片",
                "face_w": None, "shoulder_w": None}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── 人脸检测 ──────────────────────────────────────────────
    face = _detect_face(gray)
    if face is None:
        return {"ratio": None, "verdict": "NO_FACE", "error": "未检测到人脸",
                "face_w": None, "shoulder_w": None}
    _, _, face_w, _ = face

    # ── 肩膀检测 ──────────────────────────────────────────────
    sh = _detect_shoulders(model, img)
    if sh is None:
        return {"ratio": None, "verdict": "NO_SHOULDER", "error": "未检测到肩膀关键点",
                "face_w": face_w, "shoulder_w": None}

    shoulder_w, img_w = sh
    if shoulder_w < 10:
        return {"ratio": None, "verdict": "NO_SHOULDER", "error": "肩宽过小，跳过",
                "face_w": face_w, "shoulder_w": round(shoulder_w, 1)}

    ratio = face_w / shoulder_w

    if ratio > RATIO_MAX:
        verdict = "BAD_BIG"     # 脸太大
    elif ratio < RATIO_MIN:
        verdict = "BAD_SMALL"   # 脸太小
    else:
        verdict = "OK"

    return {
        "ratio":      round(ratio, 3),
        "verdict":    verdict,
        "error":      "",
        "face_w":     int(face_w),
        "shoulder_w": round(shoulder_w, 1),
    }


def main():
    input_dir  = Path(INPUT_DIR)
    bad_dir    = Path(BAD_DIR)
    report_path = Path(REPORT_CSV)

    if not input_dir.is_dir():
        raise NotADirectoryError(f"INPUT_DIR 不存在: {input_dir}")

    report_path.parent.mkdir(parents=True, exist_ok=True)

    print("⏳ 加载 YOLOv8-pose 模型（首次运行会下载 ~6MB）...")
    model = _load_pose_model()
    print("✅ 模型就绪\n")

    pattern = input_dir.rglob("*") if RECURSIVE else input_dir.iterdir()
    images  = sorted(p for p in pattern if p.is_file() and p.suffix.lower() in EXTS)
    total   = len(images)
    print(f"共找到 {total} 张图片  阈值: {RATIO_MIN} ≤ 头肩比 ≤ {RATIO_MAX}\n{'='*60}")

    rows: list[dict] = []
    cnt_ok = cnt_bad = cnt_skip = 0

    for i, img_path in enumerate(images, 1):
        res = analyze_proportion(model, img_path)
        rel = str(img_path.relative_to(input_dir))

        verdict = res["verdict"]
        ratio   = res["ratio"]

        if verdict == "OK":
            cnt_ok += 1
            emoji = "🟢"
        elif verdict in ("BAD_BIG", "BAD_SMALL"):
            cnt_bad += 1
            emoji = "🔴"
            bad_dir.mkdir(parents=True, exist_ok=True)
            dest = bad_dir / img_path.name
            if dest.exists():
                dest = bad_dir / f"{img_path.parent.name}_{img_path.name}"
            (shutil.move if MOVE_BAD_FILES else shutil.copy2)(str(img_path), str(dest))
        else:
            cnt_skip += 1
            emoji = "⚠️ "

        label = (
            f"头肩比={ratio}  头宽={res['face_w']}px  肩宽={res['shoulder_w']}px"
            if ratio is not None
            else res["error"]
        )
        print(f"  {emoji} [{i}/{total}] {img_path.name}  {label}  → {verdict}")

        rows.append({
            "file":       rel,
            "ratio":      ratio if ratio is not None else "",
            "face_w_px":  res["face_w"] or "",
            "shoulder_w_px": res["shoulder_w"] or "",
            "verdict":    verdict,
            "error":      res["error"],
        })

    # ── 写 CSV ────────────────────────────────────────────────
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "ratio", "face_w_px", "shoulder_w_px", "verdict", "error"
        ])
        writer.writeheader()
        writer.writerows(rows)

    action = "已移动" if MOVE_BAD_FILES else "已复制"
    print(f"\n{'='*60}")
    print(f"  🟢 OK            : {cnt_ok} 张")
    print(f"  🔴 BAD（比例异常）: {cnt_bad} 张（{action}到 {bad_dir}）")
    print(f"  ⚠️  跳过（无法检测）: {cnt_skip} 张")
    print(f"报告: {report_path.resolve()}")


if __name__ == "__main__":
    main()
