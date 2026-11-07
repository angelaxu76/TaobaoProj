"""
换模特后处理：只把 AI 结果图的头颈贴回原图，衣服/配件/背景全部保留原图像素。

LinkFox 换模特接口会重绘它判定为非保留区的内容（例如把包换了颜色）。
结果图与原图姿势一致、可按像素对齐，所以本地合成即可，不额外扣点。

做法：
  1. 把结果图缩放到原图尺寸
  2. 用姿态模型定位两图的头部（鼻/眼/耳关键点），确定头部附近的搜索范围
  3. 在范围内比较两图差异，取与人脸相连的变化区域（覆盖新旧头发、脖子）
  4. 羽化边缘后合成

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


def _head_mask(
    original: np.ndarray,
    swapped: np.ndarray,
    face: tuple[int, int, int, int],
) -> np.ndarray:
    """返回 float32 羽化蒙版（0~1，1 = 使用结果图）。"""
    h, w = original.shape[:2]
    x0, y0, x1, y1 = face
    fw = x1 - x0

    rx0, rx1 = max(0, int(x0 - 0.9 * fw)), min(w, int(x1 + 0.9 * fw))
    ry0, ry1 = max(0, int(y0 - 1.0 * fw)), min(h, int(y1 + 0.7 * fw))

    sigma = max(1.0, fw / 100)
    lab_o = cv2.cvtColor(cv2.GaussianBlur(original[ry0:ry1, rx0:rx1], (0, 0), sigma),
                         cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_s = cv2.cvtColor(cv2.GaussianBlur(swapped[ry0:ry1, rx0:rx1], (0, 0), sigma),
                         cv2.COLOR_BGR2LAB).astype(np.float32)
    changed = (np.linalg.norm(lab_o - lab_s, axis=2) > DIFF_THRESHOLD).astype(np.uint8)

    # 人脸框内一定替换，保证变化区域能和人脸连上
    cv2.rectangle(changed, (x0 - rx0, y0 - ry0), (x1 - rx0, y1 - ry0), 1, -1)

    k = max(3, int(fw * 0.08)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    changed = cv2.morphologyEx(changed, cv2.MORPH_CLOSE, kernel)
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, kernel)

    # 只保留与人脸相连的区域，并填掉内部空洞
    _, labels = cv2.connectedComponents(changed)
    face_label = labels[(y0 + y1) // 2 - ry0, (x0 + x1) // 2 - rx0]
    region = (labels == face_label).astype(np.uint8)
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(region, contours, -1, 1, -1)

    mask = np.zeros((h, w), np.float32)
    mask[ry0:ry1, rx0:rx1] = region
    return cv2.GaussianBlur(mask, (0, 0), max(2.0, fw * 0.03))


def composite_head(
    original: np.ndarray,
    swapped: np.ndarray,
) -> tuple[np.ndarray | None, str]:
    """把 swapped 的头颈合成到 original 上。

    Args:
        original: 原图（BGR）
        swapped:  AI 换模特结果图（BGR）

    Returns:
        (合成图, "") 成功；(None, 失败原因) 失败。合成图尺寸与原图一致。
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

    mask = _head_mask(original, resized, face)[..., None]
    merged = resized.astype(np.float32) * mask + original.astype(np.float32) * (1 - mask)
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
