"""
换模特后处理：以 AI 结果图为底，把被 AI 改掉的衣服/配件从原图贴回来。

LinkFox 换模特接口会重绘它判定为非保留区的内容（例如把包换了颜色）。
结果图与原图姿势一致、可按像素对齐，所以本地合成即可，不额外扣点。

头部区域完全保留 AI 图、不做任何拼接，因此不会出现旧头轮廓的重影。
（反过来把 AI 头贴到原图上，旧头发的轮廓总会残留。）

做法：
  1. 把结果图缩放到原图尺寸，用姿态模型定位两图的头部（鼻/眼/耳关键点）
  2. 比较头部以外的差异：没有明显差异就不处理，直接用 AI 图
  3. 有差异时，把变化区域（包、鞋、手等）从原图贴回结果图

检测不到头部（如背影）、两图头部位置不一致或对不齐时返回失败原因，
由调用方决定如何处理。
"""
import threading
from pathlib import Path

import cv2
import numpy as np

MAX_ALIGN_SHIFT_PX = 8     # 两图允许的最大整体偏移（原图像素）
MIN_ALIGN_RESPONSE = 0.1   # 相位相关置信度下限
MAX_ASPECT_DIFF    = 0.03  # 两图允许的最大宽高比差异
DIFF_THRESHOLD     = 14    # Lab 色差阈值，低于此值视为未变化
BODY_DIFF_RATIO    = 0.004 # 头部以外变化面积占比，低于此值不合成（50 对实拍图校准）

POSE_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "yolov8n-pose.pt"
KEYPOINT_MIN_CONF = 0.5
HEAD_KEYPOINTS    = slice(0, 5)  # COCO：鼻、双眼、双耳
SHOULDER_KEYPOINTS = slice(5, 7)

_pose_model = None
_pose_lock  = threading.Lock()  # 批量脚本多线程调用，模型推理串行


def _detect_head(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """返回画面中最大人物的头部框 (x0, y0, x1, y1)，检测不到返回 None。"""
    global _pose_model
    with _pose_lock:
        if _pose_model is None:
            from ultralytics import YOLO
            _pose_model = YOLO(str(POSE_MODEL_PATH))
        result = _pose_model.predict(img, verbose=False)[0]

    if result.keypoints is None or len(result.boxes) == 0:
        return None

    boxes = result.boxes.xyxy.cpu().numpy()
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    person = int(areas.argmax())
    points = result.keypoints.xy[person].cpu().numpy()
    confs  = result.keypoints.conf[person].cpu().numpy()

    head = points[HEAD_KEYPOINTS][confs[HEAD_KEYPOINTS] >= KEYPOINT_MIN_CONF]
    if len(head) < 3:  # 至少 3 个点才算看到脸，背影不处理
        return None

    size = (head.max(axis=0) - head.min(axis=0)).max() * 1.6
    shoulders = points[SHOULDER_KEYPOINTS][confs[SHOULDER_KEYPOINTS] >= KEYPOINT_MIN_CONF]
    if len(shoulders) == 2:
        size = max(size, np.linalg.norm(shoulders[0] - shoulders[1]) * 0.45)

    cx, cy = head.mean(axis=0)
    return (int(cx - size / 2), int(cy - size * 0.6),
            int(cx + size / 2), int(cy + size * 0.6))


def _body_diff_ratio(
    original: np.ndarray,
    swapped: np.ndarray,
    head: tuple[int, int, int, int],
) -> float:
    """返回头部以外发生明显变化的面积占比。"""
    scale = 800 / max(original.shape[:2])
    small = [cv2.GaussianBlur(cv2.resize(i, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                              (0, 0), 3) for i in (original, swapped)]
    lab = [cv2.cvtColor(i, cv2.COLOR_BGR2LAB).astype(np.float32) for i in small]
    changed = np.linalg.norm(lab[0] - lab[1], axis=2) > 15

    x0, y0, x1, y1 = (int(v * scale) for v in head)
    pad = int((x1 - x0) * 0.6)
    changed[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = False
    return float(changed.mean())


def _restore_mask(
    original: np.ndarray,
    swapped: np.ndarray,
    head: tuple[int, int, int, int],
) -> np.ndarray:
    """返回 float32 羽化蒙版（0~1，1 = 贴回原图）。"""
    h, w = original.shape[:2]
    scale = min(1.0, 1600 / max(h, w))
    small = [cv2.GaussianBlur(cv2.resize(i, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                              (0, 0), 1.5) for i in (original, swapped)]
    lab_o, lab_s = (cv2.cvtColor(i, cv2.COLOR_BGR2LAB).astype(np.float32) for i in small)
    sh, sw = lab_o.shape[:2]

    x0, y0, x1, y1 = (int(v * scale) for v in head)
    fw = x1 - x0
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    chin = int(cy + 0.45 * fw)
    low  = min(sh, int(cy + 1.4 * fw))

    # 这些地方保留 AI 图：下巴以上、脖子，以及旧头发原来遮住的背景
    keep = np.zeros((sh, sw), bool)
    keep[:chin, max(0, cx - int(1.1 * fw)):cx + int(1.1 * fw)] = True
    keep[:low, max(0, cx - int(0.9 * fw)):cx + int(0.9 * fw)] = True

    bx0, bx1 = max(0, cx - int(1.6 * fw)), min(sw, cx + int(1.6 * fw))
    background = np.median(small[1][:max(1, y0), bx0:bx1].reshape(-1, 3), axis=0).astype(np.uint8)
    background = cv2.cvtColor(background.reshape(1, 1, 3), cv2.COLOR_BGR2LAB).astype(np.float32)
    near_background = np.linalg.norm(lab_s[:low, bx0:bx1] - background, axis=2) < 12
    keep[:low, bx0:bx1] |= near_background

    restore = (np.linalg.norm(lab_o - lab_s, axis=2) > DIFF_THRESHOLD) & ~keep
    restore = restore.astype(np.uint8)

    k = max(3, int(fw * 0.03)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    restore = cv2.morphologyEx(restore, cv2.MORPH_OPEN, kernel)
    restore = cv2.morphologyEx(restore, cv2.MORPH_CLOSE, kernel)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(restore)
    big = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= sh * sw * 0.0003)
    restore = np.isin(labels, big[big != 0]).astype(np.uint8)

    contours, _ = cv2.findContours(restore, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(restore, contours, -1, 1, -1)
    restore = cv2.dilate(restore, kernel)
    restore[keep] = 0

    mask = cv2.resize(restore.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(mask, (0, 0), max(2.0, fw / scale * 0.015))


def composite_head(
    original: np.ndarray,
    swapped: np.ndarray,
) -> tuple[np.ndarray | None, str]:
    """把 swapped 中被改掉的衣服/配件还原成 original 的样子。

    Args:
        original: 原图（BGR）
        swapped:  AI 换模特结果图（BGR）

    Returns:
        (合成图, "") 已合成，尺寸与原图一致；(None, "") 头部以外无明显差异，
        无需合成，直接用 AI 图；(None, 失败原因) 失败。
    """
    h, w = original.shape[:2]
    aspect_diff = abs((w / h) / (swapped.shape[1] / swapped.shape[0]) - 1)
    if aspect_diff > MAX_ASPECT_DIFF:
        return None, f"宽高比不一致 ({aspect_diff:.1%})"

    resized = cv2.resize(swapped, (w, h), interpolation=cv2.INTER_CUBIC)

    gray_o = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray_s = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow((w, h), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(gray_o, gray_s, window)
    if response < MIN_ALIGN_RESPONSE or max(abs(dx), abs(dy)) > MAX_ALIGN_SHIFT_PX:
        return None, f"两图未对齐 (偏移 {dx:.1f},{dy:.1f}，置信度 {response:.2f})"

    head_o = _detect_head(original)
    head_s = _detect_head(resized)
    if not head_o or not head_s:
        return None, f"未检测到头部 (原图 {bool(head_o)}，结果图 {bool(head_s)})"

    center_gap = np.hypot((head_o[0] + head_o[2] - head_s[0] - head_s[2]) / 2,
                          (head_o[1] + head_o[3] - head_s[1] - head_s[3]) / 2)
    head_size = max(head_o[2] - head_o[0], head_s[2] - head_s[0])
    if center_gap > head_size * 0.5:
        return None, f"两图头部位置不一致 (相差 {center_gap:.0f}px，头宽 {head_size}px)"

    face = (min(head_o[0], head_s[0]), min(head_o[1], head_s[1]),
            max(head_o[2], head_s[2]), max(head_o[3], head_s[3]))

    if _body_diff_ratio(original, resized, face) < BODY_DIFF_RATIO:
        return None, ""

    mask = _restore_mask(original, resized, face)[..., None]
    merged = original.astype(np.float32) * mask + resized.astype(np.float32) * (1 - mask)
    return merged.round().astype(np.uint8), ""


def read_image(path: str) -> np.ndarray | None:
    """读取图片（支持中文路径）。"""
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)


def write_jpg(path: str, img: np.ndarray, quality: int = 95) -> None:
    """保存 JPG（支持中文路径）。"""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError(f"JPG 编码失败: {path}")
    buf.tofile(path)
