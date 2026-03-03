"""
AI 换脸图质量评分脚本。

原理：使用 OpenCV 内置 Haar cascade 检测人脸（无需额外模型下载），
从以下三个维度综合打分：
  - 颈部肤色衔接一致性    ：占 40%（色差越小越好）
  - 人脸锐度（清晰度）   ：占 30%（Laplacian 方差，越高越清晰）
  - 脸部水平居中          ：占 30%（人脸中心 vs 图片中心偏移量）

分级输出：
  excellent (90-100) → 可直接上架
  good      (70-89)  → 基本可用
  fair      (50-69)  → 边缘可用，建议人工复核
  poor      (0-49)   → 质量差，建议重新生成

用法：
  1. 修改下方"本次运行参数"。
  2. 运行：python ops/run_score_faceswap_images.py

依赖：pip install opencv-python numpy
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import shutil
import csv
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 待评分的图片目录（通常是换脸输出目录）
INPUT_DIR = r"D:\output\faceswap_output"

# 评分结果的输出根目录（会在里面创建四个子文件夹 + 汇总 CSV）
OUTPUT_DIR = r"D:\output\faceswap_scored"

# 是否把图片按分级复制到对应子目录（False = 只打印/导出 CSV，不复制文件）
COPY_TO_TIER = True

# 是否递归扫描子目录
RECURSIVE = False

# 支持的图片格式
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================

# OpenCV 内置 Haar cascade（随 opencv-python 自带，无需额外下载）
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

TIER_DIRS = {
    "excellent": "excellent_90-100",
    "good":      "good_70-89",
    "fair":      "fair_50-69",
    "poor":      "poor_0-49",
}


def _tier(score: float) -> str:
    if score >= 90: return "excellent"
    if score >= 70: return "good"
    if score >= 50: return "fair"
    return "poor"


def _sharpness(gray_region: np.ndarray) -> float:
    """Laplacian 方差：越高表示越清晰（>100 为清晰，<20 为模糊）。"""
    if gray_region.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray_region, cv2.CV_64F).var())


def analyze_faceswap(image_path: Path) -> dict:
    """
    分析换脸图片质量，返回评分 dict。
    出错时返回 {"total": 0, "error": "..."}。
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return {"total": 0, "error": "无法读取图片"}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # ── 人脸检测 ──────────────────────────────────────────────
    faces = _FACE_CASCADE.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return {"total": 0, "error": "未检测到人脸"}

    # 取面积最大的脸（换脸图通常只有一张主要人脸）
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    face_x, face_y, face_w, face_h = faces[0]
    face_center_x = face_x + face_w // 2

    scores: dict = {}

    # ── 1. 颈部肤色衔接评分（40%）─────────────────────────────
    # 取脸部下沿 15% 区域 vs 脸下方 30% 高度的颈部区域，比较 RGB 均值
    face_bottom_y = face_y + face_h
    neck_top_y    = face_bottom_y
    neck_bot_y    = min(face_bottom_y + int(face_h * 0.3), h)
    neck_x1 = face_x + face_w // 4
    neck_x2 = face_x + face_w * 3 // 4

    color_score    = 50.0
    color_diff_val = None
    if neck_bot_y > neck_top_y and neck_x2 > neck_x1:
        face_lower = img_rgb[
            max(0, face_bottom_y - int(face_h * 0.15)): face_bottom_y,
            neck_x1: neck_x2
        ]
        neck_region = img_rgb[neck_top_y: neck_bot_y, neck_x1: neck_x2]
        if face_lower.size > 0 and neck_region.size > 0:
            color_diff_val = float(np.linalg.norm(
                face_lower.mean(axis=(0, 1)) - neck_region.mean(axis=(0, 1))
            ))
            # 色差 < 5 → 100分；色差 > 55 → 0分
            color_score = max(0.0, 100.0 - color_diff_val * 2.0)

    scores["color_match"] = round(color_score, 1)
    scores["color_diff"]  = round(color_diff_val, 2) if color_diff_val is not None else None

    # ── 2. 人脸锐度评分（30%）────────────────────────────────
    face_gray = gray[face_y: face_y + face_h, face_x: face_x + face_w]
    lap_var   = _sharpness(face_gray)
    # Laplacian 方差：>=200 满分；<=10 零分
    sharp_score = min(100.0, max(0.0, (lap_var - 10) / (200 - 10) * 100))
    scores["sharpness"]    = round(sharp_score, 1)
    scores["laplacian_var"] = round(lap_var, 1)

    # ── 3. 水平居中评分（30%）────────────────────────────────
    # 人脸中心与图片中心的水平偏移，允许 10% 图宽的偏差
    offset = abs(face_center_x - w // 2)
    center_score = max(0.0, 100.0 - (offset / (w * 0.10)) * 100)
    scores["centering"]        = round(center_score, 1)
    scores["center_offset_px"] = int(offset)

    # ── 综合评分 ──────────────────────────────────────────────
    total = (
        scores["color_match"] * 0.40 +
        scores["sharpness"]   * 0.30 +
        scores["centering"]   * 0.30
    )
    scores["total"] = round(total, 1)
    return scores


def run_scoring(
    input_dir: str,
    output_dir: str,
    *,
    copy_to_tier: bool = True,
    recursive: bool = False,
) -> None:
    input_root = Path(input_dir)
    if not input_root.is_dir():
        raise NotADirectoryError(f"INPUT_DIR 不存在: {input_dir}")

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if copy_to_tier:
        for sub in TIER_DIRS.values():
            (out_root / sub).mkdir(exist_ok=True)

    pattern = input_root.rglob("*") if recursive else input_root.iterdir()
    images  = sorted(p for p in pattern if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"未找到任何图片：{input_dir}")
        return

    print(f"共找到 {len(images)} 张图片，开始评分…\n{'='*60}")

    rows: list[dict] = []
    tier_counts = {t: 0 for t in TIER_DIRS}
    skip_count  = 0

    for img_path in images:
        result = analyze_faceswap(img_path)
        rel    = str(img_path.relative_to(input_root))

        if "error" in result:
            print(f"  ⚠️  {img_path.name} → 跳过: {result['error']}")
            skip_count += 1
            rows.append({
                "file": rel, "total": "", "tier": "skip", "error": result["error"],
                "color_match": "", "color_diff": "",
                "sharpness": "", "laplacian_var": "",
                "centering": "", "center_offset_px": "",
            })
            continue

        total = result["total"]
        tier  = _tier(total)
        tier_counts[tier] += 1

        emoji = {"excellent": "🟢", "good": "🟡", "fair": "🟠", "poor": "🔴"}[tier]
        print(
            f"  {emoji} {img_path.name}  总分={total}  "
            f"肤色={result['color_match']}(色差={result.get('color_diff','N/A')})  "
            f"锐度={result['sharpness']}(Lap={result['laplacian_var']})  "
            f"居中={result['centering']}(偏移={result['center_offset_px']}px)"
        )

        if copy_to_tier:
            dst = out_root / TIER_DIRS[tier] / img_path.name
            if dst.exists():
                dst = out_root / TIER_DIRS[tier] / f"{img_path.parent.name}_{img_path.name}"
            shutil.copy2(img_path, dst)

        rows.append({
            "file":             rel,
            "total":            total,
            "tier":             tier,
            "error":            "",
            "color_match":      result["color_match"],
            "color_diff":       result.get("color_diff", ""),
            "sharpness":        result["sharpness"],
            "laplacian_var":    result["laplacian_var"],
            "centering":        result["centering"],
            "center_offset_px": result["center_offset_px"],
        })

    # 汇总 CSV
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_root / f"score_report_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "total", "tier",
            "color_match", "color_diff",
            "sharpness", "laplacian_var",
            "centering", "center_offset_px",
            "error",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"评分完成")
    print(f"  🟢 excellent (90-100): {tier_counts['excellent']} 张")
    print(f"  🟡 good      (70-89) : {tier_counts['good']} 张")
    print(f"  🟠 fair      (50-69) : {tier_counts['fair']} 张")
    print(f"  🔴 poor      (0-49)  : {tier_counts['poor']} 张")
    print(f"  ⚠️  跳过               : {skip_count} 张")
    print(f"汇总报告: {csv_path}")
    if copy_to_tier:
        print(f"分级图片: {out_root}")


def main():
    run_scoring(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        copy_to_tier=COPY_TO_TIER,
        recursive=RECURSIVE,
    )


if __name__ == "__main__":
    main()
