"""
shoe_angle_warp.py
====================
纯白底商品图小角度旋转（纯 Python / OpenCV，无扩散模型，无云端GPU）。

相较于最初版本修的两个关键问题：

1. remap 方向反了
   cv2.remap(map_x, map_y) 要求 map_x/map_y 表示"目标像素该去源图哪个坐标采样"
   （backward mapping）。原脚本算的却是"源像素旋转后跑到哪"（forward mapping），
   直接塞给 remap 方向是反的，小角度下也会出现撕裂/重影，角度越大越明显。
   这里改用标准的两遍 DIBR（Depth-Image-Based Rendering）：
     Pass 1（forward，只算深度）：把源深度按旋转矩阵投到新相机坐标系，用
       z-buffer 解决遮挡，得到"目标像素旋转后离相机多远"。
     Pass 2（backward，采样RGB）：拿着目标深度反推回原图坐标，得到真正符合
       remap 语义的 backward map，再用双线性插值采样原图。
   这样每个输出像素都是原图像素的双线性插值结果，不存在"生成"材质的风险。

2. 纯白背景被一起卷入 warp/inpaint，边缘容易发虚
   商业图背景是纯白色、无纹理，深度模型在这种区域的估计基本是噪声。
   这里先用简单阈值把鞋子从纯白底抠出来，只对鞋子区域做重投影；背景画布
   全程保持纯白 (255,255,255)，不需要对背景做任何 inpaint。
   鞋身内部因自遮挡产生的空洞（5°小角度下通常极少，多见于鞋底/后跟这种
   深度突变处）才会落到 inpaint，且被严格限制在鞋子轮廓内的窄条区域。

3. 抠图阈值写死 246，实拍图背景不一定是纯 255
   webp/jpg 压缩后背景常见 244~254 之间的均匀灰度而非严格 255。曾经硬编码
   white_thresh=246 时，只要背景灰度恰好落在阈值上，会被误判成"鞋子"，
   导致 shoe_mask 覆盖了几乎整张图，深度归一化被背景噪声稀释，旋转视差
   被压得几乎看不出来。segment_shoe_on_white 现在从图片四周边框实测背景
   灰度、动态定阈值，不管背景是 255 还是压缩后的 246 都能正确抠出来。

4. 轮廓边缘（尤其掠射角边，比如鞋筒后侧、系带排）warp 后出现发白描边/断线
   shoe_mask 曾经朝外膨胀 1px，把鞋子和背景之间的抗锯齿过渡像素（颜色是两者
   混合、深度也不可靠）当成了真实鞋子表面参与3D重投影。backward_sample_rgb
   反推回这些像素时采到的是偏灰白的过渡色，warp 后就在轮廓边上留下一圈很窄
   的白边，在合成阶段用羽化/腐蚀 dest_mask 去补救效果有限。真正的修法是在
   segment_shoe_on_white 里把 mask 向内腐蚀几像素（erode_px），从源头把这些
   不可靠的过渡像素排除在计算之外，而不是等 warp 完了再去描边上打补丁。

依赖：
  pip install opencv-python-headless numpy torch transformers pillow
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


# --------------------------------------------------------------------------
# 1. 深度估计
# --------------------------------------------------------------------------

def estimate_depth_offline_demo(image_path: str):
    """离线演示用：不下载模型，用一个中心近/边缘远的伪深度验证warp流程本身。"""
    pil_img = Image.open(image_path).convert("RGB")
    img_np = np.array(pil_img)
    h, w = img_np.shape[:2]

    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    cx, cy = w * 0.5, h * 0.62
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    dist_norm = dist / dist.max()
    depth = 1.0 - dist_norm
    depth = cv2.GaussianBlur(depth.astype(np.float32), (31, 31), 0)
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-6)
    return depth, pil_img


def estimate_depth(image_path: str):
    """
    用 Depth-Anything V2 (small) 估计相对深度，返回 0-1 归一化数组。

    注意：Depth-Anything 系列输出的是"近大远小"的相对深度/视差（数值越大越近），
    和我们需要的相机坐标系 Z（越大越远）方向相反，estimate_depth 只负责返回
    模型原始的归一化输出；是否取反交给 depth_to_far_map 的 invert 参数处理，
    便于你用 --save-depth 看一眼再决定。
    """
    import torch
    from transformers import pipeline

    depth_pipe = pipeline(
        task="depth-estimation",
        model="depth-anything/Depth-Anything-V2-Small-hf",
        device=0 if torch.cuda.is_available() else -1,
    )
    img = Image.open(image_path).convert("RGB")
    result = depth_pipe(img)
    depth = np.array(result["depth"], dtype=np.float32)
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-6)
    return depth, img


def depth_to_far_map(depth01: np.ndarray, shoe_mask: np.ndarray,
                      real_span_mm: float = 90.0, base_mm: float = 400.0,
                      invert: bool = False) -> np.ndarray:
    """
    把 0-1 相对深度换算成相机坐标系下的 Z（毫米，越大越远）。

    没有用原脚本里 depth_scale_mm=500 这种和图像分辨率/焦距无关的固定常数，
    而是把深度起伏幅度 (real_span_mm) 绑定到"鞋子这种物体大概有多厚/多立体"
    的物理直觉上——不管输入图片分辨率多大，视差效果都基本一致。
    """
    far = (1.0 - depth01) if invert else depth01.copy()
    # 只用鞋子区域的分布做归一化，避免纯白背景的噪声拉伸整体范围
    vals = far[shoe_mask > 0]
    if vals.size == 0:
        vals = far.reshape(-1)
    lo, hi = np.percentile(vals, 1), np.percentile(vals, 99)
    far = np.clip((far - lo) / (hi - lo + 1e-6), 0.0, 1.0)
    far = cv2.bilateralFilter(far.astype(np.float32), d=9, sigmaColor=0.15, sigmaSpace=9)
    return far * real_span_mm + base_mm


# --------------------------------------------------------------------------
# 2. 纯白背景抠图（不依赖任何分割模型）
# --------------------------------------------------------------------------

def segment_shoe_on_white(img_bgr: np.ndarray, white_tolerance: int = 12,
                           min_area_ratio: float = 0.01, erode_px: int = 3) -> np.ndarray:
    """
    纯白底图抠鞋子：非背景色像素 = 前景。返回 0/255 的 uint8 mask。

    背景色不写死 255——实拍图/webp 压缩后背景经常是 244~254 之间的均匀灰度，
    不是严格的纯白。之前硬编码 white_thresh=246 时，只要背景刚好落在阈值上
    （src <= thresh 判定为前景），整张背景会被误判成"鞋子"，导致后续深度归一化
    被背景噪声稀释、旋转视差被压得几乎看不出来。这里改成从图片四周边框实测
    背景灰度，再留一点容差，不管背景是 255 还是压缩后的 246 都能正确抠出来。
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    border = np.concatenate([
        gray[:20, :].ravel(), gray[-20:, :].ravel(),
        gray[:, :20].ravel(), gray[:, -20:].ravel(),
    ])
    bg_level = int(np.median(border))
    white_thresh = bg_level - white_tolerance
    print(f"[诊断] 实测背景灰度中位数={bg_level}, 抠图阈值={white_thresh}")
    _, mask = cv2.threshold(gray, white_thresh, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # 只保留最大连通域（鞋子），去掉可能残留的阴影/水印噪点
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        biggest = 1 + int(np.argmax(areas))
        if areas.max() >= mask.size * min_area_ratio:
            mask = np.where(labels == biggest, 255, 0).astype(np.uint8)

    # 向内收缩几像素，把"鞋子和背景的抗锯齿过渡像素"排除在参与3D重投影的
    # 源数据之外。这几像素颜色是鞋子和背景的混合色，深度也不可靠，一旦被
    # 当作真实鞋子表面去做旋转采样，warp 后会在轮廓边缘（尤其是鞋筒后侧、
    # 系带排这种接近掠射角的边）产生一圈发白的描边/断线，且没法在合成阶段
    # 靠羽化/腐蚀 mask 补救干净——必须在源头就不让这些像素进入计算。
    if erode_px > 0:
        mask = cv2.erode(mask, np.ones((erode_px * 2 + 1, erode_px * 2 + 1), np.uint8))
    return mask


# --------------------------------------------------------------------------
# 3. 相机几何
# --------------------------------------------------------------------------

@dataclass
class CameraGeom:
    K: np.ndarray
    K_inv: np.ndarray
    R: np.ndarray
    center: np.ndarray  # 旋转支点：鞋子质心（相机坐标系，毫米）——不是相机原点


def build_camera(w: int, h: int, azimuth_deg: float, elevation_deg: float = 0.0,
                  focal_ratio: float = 1.4) -> CameraGeom:
    """
    focal_ratio 相对图像宽度定焦距，换分辨率不用重新调参数。
    center 先占位成原点，算出鞋子质心后由 run() 回填 geom.center。
    """
    f = w * focal_ratio
    K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]], dtype=np.float64)
    K_inv = np.linalg.inv(K)

    az, el = np.deg2rad(azimuth_deg), np.deg2rad(elevation_deg)
    Ry = np.array([[np.cos(az), 0, np.sin(az)], [0, 1, 0], [-np.sin(az), 0, np.cos(az)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(el), -np.sin(el)], [0, np.sin(el), np.cos(el)]])
    R = Rx @ Ry
    return CameraGeom(K=K, K_inv=K_inv, R=R, center=np.zeros(3))


def compute_object_center_mm(far_mm: np.ndarray, shoe_mask: np.ndarray, K_inv: np.ndarray) -> np.ndarray:
    """
    鞋子质心（相机坐标系，毫米）。旋转必须绕这个点转，不能绕相机原点转——
    绕相机原点转在数学上约等于一次纯2D homography，几乎不依赖深度，所以
    5°转出来跟没转一样；绕物体质心转，才等价于"鞋子在转盘上转5°"：
    离相机近的点和远的点会产生不同的位移（视差），旋转效果才会真的可见。
    """
    ys, xs = np.where(shoe_mask > 0)
    z = far_mm[ys, xs]
    pix = np.stack([xs, ys, np.ones_like(xs)], axis=-1).astype(np.float64)
    rays = pix @ K_inv.T
    pts = rays * z[:, None]
    return pts.mean(axis=0)


# --------------------------------------------------------------------------
# 4. 两遍 DIBR：forward 深度 z-buffer -> backward RGB 采样
# --------------------------------------------------------------------------

def forward_scatter_depth(far_mm: np.ndarray, shoe_mask: np.ndarray, geom: CameraGeom):
    """Pass 1: 只把深度按旋转矩阵投过去，z-buffer 取每个目标像素最近的点。"""
    h, w = far_mm.shape
    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    ys, xs = ys[shoe_mask > 0], xs[shoe_mask > 0]
    z_src = far_mm[shoe_mask > 0]

    pix = np.stack([xs, ys, np.ones_like(xs)], axis=-1).astype(np.float64)
    rays = pix @ geom.K_inv.T                      # z 分量恒为 1
    pts_src = rays * z_src[:, None]                 # 源相机坐标系下的 3D 点

    pts_dst = (pts_src - geom.center) @ geom.R.T + geom.center  # 绕鞋子质心转，不是绕相机原点
    proj = pts_dst @ geom.K.T
    z_dst = pts_dst[:, 2]
    u = proj[:, 0] / (z_dst + 1e-6)
    v = proj[:, 1] / (z_dst + 1e-6)

    # 诊断：这次旋转实际把鞋子像素挪动了多少像素——如果中位数只有个位数，
    # 说明角度/质心设置仍然偏保守，视觉上大概率还是看不出来
    disp = np.sqrt((u - xs) ** 2 + (v - ys) ** 2)
    print(f"[诊断] 像素位移: 中位数={np.median(disp):.2f}px, 最大={disp.max():.2f}px, "
          f"质心(mm)={geom.center}")

    dest_far = np.full((h, w), np.inf, dtype=np.float64)
    ui, vi = np.round(u).astype(np.int64), np.round(v).astype(np.int64)
    valid = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h) & (z_dst > 0)
    ui, vi, zd = ui[valid], vi[valid], z_dst[valid]

    # z-buffer：同一目标像素只保留离相机最近（z 最小）的深度
    flat_idx = vi * w + ui
    np.minimum.at(dest_far.reshape(-1), flat_idx, zd)

    dest_mask = np.isfinite(dest_far).astype(np.uint8) * 255
    # forward 点云投影天然会有零星像素级空隙，闭运算+中值补一下，
    # 这一步只作用在深度通道上，不碰 RGB，不存在“修图”风险
    kernel = np.ones((3, 3), np.uint8)
    dest_mask_closed = cv2.morphologyEx(dest_mask, cv2.MORPH_CLOSE, kernel)
    filled = dest_far.copy()
    filled[~np.isfinite(filled)] = 0
    filled = cv2.medianBlur(filled.astype(np.float32), 3)
    dest_far = np.where((dest_mask_closed > 0) & ~np.isfinite(dest_far), filled, dest_far)

    return dest_far, dest_mask_closed


def backward_sample_rgb(img_bgr: np.ndarray, dest_far: np.ndarray, dest_mask: np.ndarray,
                         geom: CameraGeom):
    """Pass 2: 用目标深度反推回源图坐标，生成真正的 backward map 给 remap 用。"""
    h, w = dest_far.shape
    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    pix = np.stack([xs, ys, np.ones_like(xs)], axis=-1).astype(np.float64)
    rays_dst = pix @ geom.K_inv.T

    z = np.where(dest_mask > 0, dest_far, 1.0)
    pts_dst = rays_dst * z[..., None]

    # 正向是 pts_dst = (pts_src - center) @ R.T + center，
    # 反向就是 pts_src = (pts_dst - center) @ R + center（R 正交，R^-1 = R.T）
    pts_src = (pts_dst.reshape(-1, 3) - geom.center) @ geom.R + geom.center
    proj_src = pts_src @ geom.K.T
    proj_src = proj_src.reshape(h, w, 3)

    map_x = (proj_src[..., 0] / (proj_src[..., 2] + 1e-6)).astype(np.float32)
    map_y = (proj_src[..., 1] / (proj_src[..., 2] + 1e-6)).astype(np.float32)

    warped = cv2.remap(img_bgr, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return warped


# --------------------------------------------------------------------------
# 5. 合成：纯白画布 + 羽化边缘 + 仅对自遮挡空洞做窄范围 inpaint
# --------------------------------------------------------------------------

def composite_on_white(warped: np.ndarray, dest_mask: np.ndarray, feather_px: int = 2):
    """轻微羽化过渡到纯白画布。抗锯齿过渡像素已经在 segment_shoe_on_white 里
    从源头排除了，这里不需要再对 dest_mask 做额外腐蚀。"""
    alpha = cv2.GaussianBlur(dest_mask.astype(np.float32) / 255.0,
                              (feather_px * 2 + 1, feather_px * 2 + 1), 0)[..., None]
    white = np.full_like(warped, 255)
    return (warped.astype(np.float32) * alpha + white.astype(np.float32) * (1 - alpha)).astype(np.uint8)


def inpaint_self_occlusion_holes(composited: np.ndarray, dest_mask: np.ndarray,
                                  hole_mask: np.ndarray) -> tuple[np.ndarray, float]:
    """只在鞋子轮廓内部（不是背景）修补真正的自遮挡空洞，5°小角度下通常没有。"""
    holes_inside_shoe = cv2.bitwise_and(hole_mask, dest_mask)
    ratio = (holes_inside_shoe > 0).sum() / max((dest_mask > 0).sum(), 1) * 100
    if ratio == 0:
        return composited, ratio
    kernel = np.ones((3, 3), np.uint8)
    holes_inside_shoe = cv2.dilate(holes_inside_shoe, kernel, iterations=1)
    result = cv2.inpaint(composited, holes_inside_shoe, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return result, ratio


# --------------------------------------------------------------------------
# 6. 顶层入口
# --------------------------------------------------------------------------

@dataclass
class WarpJob:
    image_path: str          # 输入图片路径
    azimuth_deg: float = 5.0  # 旋转角度，正负表示左右方向，自行试
    out_dir: str = "output"   # 输出目录，自动创建
    offline_demo: bool = False  # True = 不调用深度模型，仅用于验证warp机制本身
    save_debug: bool = False    # True = 额外保存 mask / depth 可视化图


def run(job: WarpJob) -> Path:
    print(f"[1/4] 估计深度: {job.image_path}")
    depth01, pil_img = (estimate_depth_offline_demo(job.image_path) if job.offline_demo
                         else estimate_depth(job.image_path))
    img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    h, w = img_bgr.shape[:2]

    print("[2/4] 纯白背景抠图")
    shoe_mask = segment_shoe_on_white(img_bgr)
    far_mm = depth_to_far_map(depth01, shoe_mask)

    print(f"[3/4] 深度重投影旋转 {job.azimuth_deg} 度（绕鞋子质心转，forward 深度 -> backward RGB 双通）")
    geom = build_camera(w, h, job.azimuth_deg)
    geom.center = compute_object_center_mm(far_mm, shoe_mask, geom.K_inv)
    dest_far, dest_mask = forward_scatter_depth(far_mm, shoe_mask, geom)
    warped = backward_sample_rgb(img_bgr, dest_far, dest_mask, geom)

    print("[4/4] 合成到纯白画布 + 自遮挡空洞修补")
    composited = composite_on_white(warped, dest_mask)
    hole_mask = np.where(np.isfinite(dest_far), 0, 255).astype(np.uint8)
    result, hole_ratio = inpaint_self_occlusion_holes(composited, dest_mask, hole_mask)

    out_dir = Path(job.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(job.image_path).stem
    out_path = out_dir / f"{stem}_az{job.azimuth_deg:+.1f}_final.png"
    cv2.imwrite(str(out_path), result)
    if job.save_debug:
        cv2.imwrite(str(out_dir / f"{stem}_mask.png"), dest_mask)
        cv2.imwrite(str(out_dir / f"{stem}_depth.png"), (far_mm / far_mm.max() * 255).astype(np.uint8))

    print(f"完成。鞋身自遮挡空洞占比: {hole_ratio:.3f}%（背景不计入，背景全程纯白，未做任何inpaint）")
    print(f"输出: {out_path}")
    return out_path


# ============================================================
# 在这里直接改参数，不用命令行传参
# ============================================================
JOBS = [
    WarpJob(image_path=r"D:\temp\imageInput\原图.webp", azimuth_deg=5.0, out_dir=r"D:\temp\imageOutput", save_debug=True),
    # WarpJob(image_path=r"D:\temp\imageInput\26185512_GW_4.webp", azimuth_deg=-5.0, out_dir=r"D:\temp\imageOutput", save_debug=True),
]


if __name__ == "__main__":
    for job in JOBS:
        run(job)
