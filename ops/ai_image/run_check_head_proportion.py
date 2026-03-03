"""
换脸图头身比例检测脚本。

原理：
  - YOLOv8-pose 检测左右肩膀关键点 → 计算肩宽
  - OpenCV Haar cascade 检测人脸矩形 → 计算头宽
  - 头宽 / 肩宽 = 头肩比
      正常时装摄影：0.38 ~ 0.58
      换脸图脸太大：> 0.65（主要问题）
      头太小（极少）：< 0.30
  - 侧面/斜面站姿自动识别：肩宽视觉变窄导致比例虚高，
    对侧面姿态放宽阈值至 RATIO_MAX_SIDE（默认 0.85），避免误判
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
INPUT_DIR  = r"D:\barbour\faceswap_output"

# 比例不合格的图片移动到这里
BAD_DIR    = r"D:\barbour\faceswap_bad_proportion"

# 报告 CSV 路径
REPORT_CSV = r"D:\barbour\proportion_report.csv"

# 头肩比阈值：超出此范围则判定为 BAD
# 正常范围 0.38~0.58；换脸图脸太大通常 > 0.65
RATIO_MIN      = 0.30   # 低于此值：头太小（极少见）
RATIO_MAX      = 0.65   # 高于此值：脸太大（换脸主要问题）
RATIO_MAX_SIDE = 0.85   # 侧面站姿放宽阈值（肩宽视觉变窄，比例天然偏高）

# 低质量图片：True=移动（原文件消失），False=复制（原文件保留）
MOVE_BAD_FILES = True

# 是否递归扫描子目录
RECURSIVE = False

# 支持的图片格式
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================

# YOLOv8-pose 关键点索引（COCO 格式）
_KP_NOSE           = 0
_KP_LEFT_SHOULDER  = 5
_KP_RIGHT_SHOULDER = 6
_KP_LEFT_HIP       = 11
_KP_RIGHT_HIP      = 12

# 肩膀关键点置信度阈值（低于此值的点视为未检测到）
_KP_CONF_THRESHOLD = 0.3

# 侧面姿态判断参数
# 两肩置信度差值超过此值 且 较低一侧低于 _SIDE_MIN_CONF → 判定为侧面
_SIDE_CONF_DIFF  = 0.35
_SIDE_MIN_CONF   = 0.45
# 鼻尖超出肩宽范围的比例超过此值 → 判定为侧面（0.15 = 肩宽的 15%）
_SIDE_NOSE_RATIO = 0.15

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


def _detect_shoulders(model, img_bgr: np.ndarray) -> dict | None:
    """
    用 YOLOv8-pose 检测肩膀关键点。
    返回 dict:
        shoulder_w  — 肩宽（像素）
        img_w       — 图片宽度
        ls_conf     — 左肩置信度
        rs_conf     — 右肩置信度
        ls_x        — 左肩 x 坐标
        rs_x        — 右肩 x 坐标
        nose_x      — 鼻尖 x 坐标（None=未检测到）
        nose_conf   — 鼻尖置信度
    未检测到返回 None。
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

    # 鼻尖关键点（用于侧面判断）
    nose_x = nose_conf = None
    if best_kps.shape[0] > _KP_NOSE:
        nose = best_kps[_KP_NOSE]
        nose_conf = float(nose[2])
        if nose_conf > _KP_CONF_THRESHOLD:
            nose_x = float(nose[0])

    return {
        "shoulder_w": shoulder_width,
        "img_w":      float(img_bgr.shape[1]),
        "ls_conf":    float(ls[2]),
        "rs_conf":    float(rs[2]),
        "ls_x":       float(ls[0]),
        "rs_x":       float(rs[0]),
        "nose_x":     nose_x,
        "nose_conf":  nose_conf or 0.0,
    }


def _is_side_pose(sh: dict) -> bool:
    """
    判断是否为侧面/斜面站姿。
    两个条件之一满足即判定为侧面：
      1. 两肩置信度相差 > _SIDE_CONF_DIFF 且 较低一侧 < _SIDE_MIN_CONF
         （侧面时被遮挡的肩膀置信度明显下降）
      2. 鼻尖 x 超出肩膀 x 范围（鼻尖飘出肩宽区间表示脸朝向侧面）
    """
    ls_conf, rs_conf = sh["ls_conf"], sh["rs_conf"]
    ls_x,    rs_x    = sh["ls_x"],    sh["rs_x"]
    nose_x,  nose_conf = sh["nose_x"], sh["nose_conf"]

    # 条件 1：一侧肩膀置信度明显低于另一侧
    if (abs(ls_conf - rs_conf) > _SIDE_CONF_DIFF
            and min(ls_conf, rs_conf) < _SIDE_MIN_CONF):
        return True

    # 条件 2：鼻尖超出肩宽范围
    if nose_x is not None and nose_conf > _KP_CONF_THRESHOLD:
        x_min  = min(ls_x, rs_x)
        x_max  = max(ls_x, rs_x)
        span   = x_max - x_min
        margin = span * _SIDE_NOSE_RATIO
        if nose_x < x_min - margin or nose_x > x_max + margin:
            return True

    return False


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
                "face_w": face_w, "shoulder_w": None, "side_pose": False}

    shoulder_w = sh["shoulder_w"]
    if shoulder_w < 10:
        return {"ratio": None, "verdict": "NO_SHOULDER", "error": "肩宽过小，跳过",
                "face_w": face_w, "shoulder_w": round(shoulder_w, 1), "side_pose": False}

    side_pose  = _is_side_pose(sh)
    ratio_max  = RATIO_MAX_SIDE if side_pose else RATIO_MAX
    ratio      = face_w / shoulder_w

    if ratio > ratio_max:
        verdict = "BAD_BIG"
    elif ratio < RATIO_MIN:
        verdict = "BAD_SMALL"
    else:
        verdict = "OK"

    return {
        "ratio":      round(ratio, 3),
        "verdict":    verdict,
        "error":      "",
        "face_w":     int(face_w),
        "shoulder_w": round(shoulder_w, 1),
        "side_pose":  side_pose,
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
    print(f"共找到 {total} 张图片  正面阈值: {RATIO_MIN}~{RATIO_MAX}  侧面阈值: {RATIO_MIN}~{RATIO_MAX_SIDE}\n{'='*60}")

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

        side_tag = "  [侧面]" if res.get("side_pose") else ""
        label = (
            f"头肩比={ratio}  头宽={res['face_w']}px  肩宽={res['shoulder_w']}px{side_tag}"
            if ratio is not None
            else res["error"]
        )
        print(f"  {emoji} [{i}/{total}] {img_path.name}  {label}  → {verdict}")

        rows.append({
            "file":          rel,
            "ratio":         ratio if ratio is not None else "",
            "face_w_px":     res["face_w"] or "",
            "shoulder_w_px": res["shoulder_w"] or "",
            "side_pose":     "Y" if res.get("side_pose") else "",
            "verdict":       verdict,
            "error":         res["error"],
        })

    # ── 写 CSV ────────────────────────────────────────────────
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "ratio", "face_w_px", "shoulder_w_px", "side_pose", "verdict", "error"
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
