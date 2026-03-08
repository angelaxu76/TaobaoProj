"""
换脸图质量对比脚本（去脸后相似度检测）。

原理：
  - 在原图中检测人脸区域，将脸部 + 周边遮掉，
    只对「身体/衣服」区域计算 SSIM，
    分数低 = 衣服被改动 = 换脸质量差。

输入：
  FACESWAP_DIR  换脸后图片目录（文件名形如 MWX0698OL71_front_3_faceswap.jpg）
  ORIG_DIR      原图目录（自动匹配 MWX0698OL71_front_3.*，支持不同后缀）

输出：
  BAD_DIR       分数低于阈值的图片被移动（或复制）到这里
  REPORT_CSV    完整分数报告（UTF-8 with BOM，Excel 直接打开）

用法：
  1. 修改下方"运行参数"。
  2. python ops/run_compare_faceswap_quality.py

依赖：pip install opencv-python scikit-image numpy
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/ai_image/
from _session_config import FACESWAP_DIR, PERSON_DIR, FACESWAP_BAD_DIR, COMPARE_CSV

import csv
import shutil
from pathlib import Path

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

# ============================================================
# 运行参数（按需修改）— 路径由 _session_config.py 统一管理
# ============================================================

FACESWAP_DIR = str(FACESWAP_DIR)   # 换脸后图片目录
ORIG_DIR     = str(PERSON_DIR)      # 原图目录
BAD_DIR      = str(FACESWAP_BAD_DIR)
REPORT_CSV   = str(COMPARE_CSV)

# SSIM 阈值：低于此值视为「衣服被改动」→ 移入 BAD_DIR
# 建议先跑一批看分数分布再调，换脸图一般落在 0.88~0.96 之间
THRESHOLD = 0.90

# 换脸文件名在原图名后追加的后缀（不含扩展名）
FACESWAP_SUFFIX = "_faceswap"

# 脸部遮罩的扩展比例（0.45 = 脸框向外扩 45%，盖住脖子/发际线）
FACE_PAD_RATIO = 0.45

# 低质量图片：True=移动（原文件消失），False=复制（原文件保留）
MOVE_BAD_FILES = True

# 支持的图片格式
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================


def _read_img(path: Path) -> np.ndarray:
    """兼容中文路径的图片读取。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"无法读取: {path}")
    return img


def _resize_to_match(ref: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """把 target 缩放到与 ref 同尺寸；若 ref 超过 1400px 先缩放 ref。"""
    h, w = ref.shape[:2]
    max_side = 1400
    if max(h, w) > max_side:
        s = max_side / float(max(h, w))
        ref = cv2.resize(ref, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
        h, w = ref.shape[:2]
    target = cv2.resize(target, (w, h), interpolation=cv2.INTER_AREA)
    return ref, target


def _detect_faces(img_bgr: np.ndarray) -> np.ndarray:
    """使用 OpenCV 内置 Haar cascade 检测人脸，返回 [(x,y,w,h), ...] 数组。"""
    gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))


def _build_body_mask(shape_hw: tuple, faces: np.ndarray, pad_ratio: float) -> np.ndarray:
    """
    生成保留区域掩码（255=保留，0=忽略）。
    脸部及扩展区域设为 0，其余（衣服/身体）设为 255。
    """
    h, w = shape_hw
    mask = np.full((h, w), 255, dtype=np.uint8)
    for (x, y, fw, fh) in faces:
        pad = int(max(fw, fh) * pad_ratio)
        x1 = max(0, x - pad);    y1 = max(0, y - pad)
        x2 = min(w, x + fw + pad); y2 = min(h, y + fh + pad)
        mask[y1:y2, x1:x2] = 0
    return mask


def _masked_ssim(a_bgr: np.ndarray, b_bgr: np.ndarray, mask: np.ndarray) -> float:
    """
    只在 mask=255 的区域计算 SSIM（去脸后的身体/衣服相似度）。
    返回 0.0~1.0，越高越相似（衣服越没有被改）。
    """
    a = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2GRAY)
    keep = mask > 0

    # 有效像素太少则无法评估，返回 0
    MIN_PIXELS = 5000
    if keep.sum() < MIN_PIXELS:
        return 0.0

    # win_size 必须 <= 图片短边且为奇数，至少 3
    h, w = a.shape[:2]
    win = min(7, h, w)
    if win % 2 == 0:
        win -= 1
    win = max(3, win)

    _, diff = ssim(a, b, full=True, data_range=255, win_size=win)
    return float(diff[keep].mean())


def _build_orig_index(orig_dir: Path) -> dict[str, Path]:
    """
    遍历原图目录建立 stem → Path 索引。
    同 stem 多后缀时优先顺序：png > jpg/jpeg > webp。
    """
    priority = {".png": 0, ".jpg": 1, ".jpeg": 2, ".webp": 3}
    idx: dict[str, Path] = {}
    for p in orig_dir.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in EXTS):
            continue
        key = p.stem
        if key not in idx or priority.get(p.suffix.lower(), 99) < priority.get(idx[key].suffix.lower(), 99):
            idx[key] = p
    return idx


def _base_stem(faceswap_stem: str) -> str:
    """MWX0698OL71_front_3_faceswap → MWX0698OL71_front_3"""
    if faceswap_stem.endswith(FACESWAP_SUFFIX):
        return faceswap_stem[: -len(FACESWAP_SUFFIX)]
    return faceswap_stem.replace(FACESWAP_SUFFIX, "")


def main():
    faceswap_dir = Path(FACESWAP_DIR)
    orig_dir     = Path(ORIG_DIR)
    bad_dir      = Path(BAD_DIR)
    report_path  = Path(REPORT_CSV)

    if not faceswap_dir.is_dir():
        raise NotADirectoryError(f"FACESWAP_DIR 不存在: {faceswap_dir}")
    if not orig_dir.is_dir():
        raise NotADirectoryError(f"ORIG_DIR 不存在: {orig_dir}")

    report_path.parent.mkdir(parents=True, exist_ok=True)

    print("🔍 建立原图索引…")
    orig_index = _build_orig_index(orig_dir)
    print(f"   原图共 {len(orig_index)} 张")

    # 收集换脸图
    faceswap_files = sorted(
        p for p in faceswap_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTS
    )
    total = len(faceswap_files)
    print(f"   换脸图共 {total} 张，阈值 SSIM ≥ {THRESHOLD}\n{'='*60}")

    rows: list[dict] = []
    cnt_ok = cnt_bad = cnt_missing = cnt_error = 0

    for i, fs in enumerate(faceswap_files, 1):
        base   = _base_stem(fs.stem)
        orig_p = orig_index.get(base)

        # ── 找不到原图 ──────────────────────────────────────────
        if orig_p is None:
            print(f"  ⚠️  [{i}/{total}] {fs.name} → 找不到原图（base={base}）")
            cnt_missing += 1
            rows.append({
                "faceswap_file": str(fs), "orig_file": "", "base_name": base,
                "non_face_ssim": "", "faces_detected": "", "verdict": "MISSING_ORIG",
            })
            continue

        # ── 计算相似度 ────────────────────────────────────────────
        try:
            orig_img = _read_img(orig_p)
            swap_img = _read_img(fs)
            orig_img, swap_img = _resize_to_match(orig_img, swap_img)

            faces  = _detect_faces(orig_img)
            n_face = len(faces)
            mask   = _build_body_mask(orig_img.shape[:2], faces, FACE_PAD_RATIO)
            score  = _masked_ssim(orig_img, swap_img, mask)

            if score >= THRESHOLD:
                verdict = "OK"
                cnt_ok += 1
                emoji = "🟢"
            else:
                verdict = "BAD"
                cnt_bad += 1
                emoji = "🔴"
                bad_dir.mkdir(parents=True, exist_ok=True)
                dest = bad_dir / fs.name
                if MOVE_BAD_FILES:
                    shutil.move(str(fs), str(dest))
                else:
                    shutil.copy2(str(fs), str(dest))

            print(
                f"  {emoji} [{i}/{total}] {fs.name}  "
                f"SSIM={score:.4f}  脸数={n_face}  → {verdict}"
            )
            rows.append({
                "faceswap_file": str(fs), "orig_file": str(orig_p), "base_name": base,
                "non_face_ssim": f"{score:.4f}", "faces_detected": str(n_face),
                "verdict": verdict,
            })

        except Exception as e:
            cnt_error += 1
            print(f"  ❌ [{i}/{total}] {fs.name} → 出错: {e}")
            rows.append({
                "faceswap_file": str(fs), "orig_file": str(orig_p), "base_name": base,
                "non_face_ssim": "", "faces_detected": "", "verdict": f"ERROR: {e}",
            })

    # ── 写报告 ────────────────────────────────────────────────────
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "faceswap_file", "orig_file", "base_name",
            "non_face_ssim", "faces_detected", "verdict",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"总计扫描: {total}")
    print(f"  🟢 OK  : {cnt_ok}")
    print(f"  🔴 BAD : {cnt_bad}（{'已移动' if MOVE_BAD_FILES else '已复制'}到 {bad_dir}）")
    print(f"  ⚠️  无原图: {cnt_missing}")
    print(f"  ❌ 出错 : {cnt_error}")
    print(f"报告: {report_path.resolve()}")


if __name__ == "__main__":
    main()
