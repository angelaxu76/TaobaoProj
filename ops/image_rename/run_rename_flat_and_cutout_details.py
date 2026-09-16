"""
Barbour 细节图流水线：改名 -> 抠图（不加水印）-> 最大化裁剪为正方形。

步骤：
  1) 调用 run_rename_barbour_details.rename_details
     LCA0416BK11_6.jpg -> LCA0416BK11_details.jpg（同编码只改第一张）
  2) 对改名后的 *_details 图抠图（rembg birefnet-general），去掉商品周围背景
     - 不加任何水印
  3) 最大化裁剪：先按 alpha、再按近白阈值，把商品四周可删除的白色/透明区域
     全部裁掉（阈值只吃近白像素，不会裁到商品本身），
     然后把短边补白，正方形居中输出
  4) 输出 JPG 到 OUTPUT_DIR

用法：
  python ops/linkfox/run_rename_and_cutout_details.py
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, _HERE)

import numpy as np
from PIL import Image

from run_rename_barbour_details import rename_details

# ============================================================
# 运行参数（按需修改）
# ============================================================

# 原始细节图目录（会就地改名）
SOURCE_DIR = r"D:\TB\Products\barbour\repulibcation\classify\平铺"

# 抠图 + 正方形处理后的输出目录
OUTPUT_DIR = r"D:\TB\Products\barbour\repulibcation\classify\平铺_processed"

# 改名步骤：先只预览，确认无误后设为 False 实际执行
RENAME_DRY_RUN = False

# 是否执行抠图（False = 只做最大化裁剪 + 正方形，不调用 rembg）
AUTO_CUTOUT = True

# 已是白底的图跳过抠图（细节图多为白底，开启可提速；关掉则全部强制抠图）
WHITE_BG_SKIP = False

# 近白阈值：RGB 三通道都 >= 该值的像素视为"可删除白色"（越小裁得越狠）
# 245 较保守，235~240 更激进；商品本身像素一般远低于此值，不会被裁到
WHITE_THRESHOLD = 244

# 裁剪后向外保留的白边留白（px），0 = 紧贴商品
MARGIN_PX = 8

# 输出统一边长（px）；None = 保持裁剪后的原始尺寸
TARGET_SIZE = 1500

# JPG 质量
JPEG_QUALITY = 95

# 并发线程数（rembg 推理 CPU 密集，建议 <= 4）
MAX_WORKERS = 2

# ============================================================

import helper.image.cut_square_white_watermark as _mod

_mod.AUTO_CUTOUT   = AUTO_CUTOUT
_mod.WHITE_BG_SKIP = WHITE_BG_SKIP
_mod.DIAGONAL_TEXT_ENABLE = False
_mod.LOCAL_LOGO_ENABLE    = False

_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _flatten_to_white(img: Image.Image) -> Image.Image:
    """把（可能带 alpha 的）图合成到白底，返回 RGB。"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        white = Image.new("RGB", rgba.size, (255, 255, 255))
        white.paste(rgba, mask=rgba.split()[-1])
        return white
    return img.convert("RGB")


def _content_bbox(rgb: Image.Image, thr: int, margin: int) -> tuple[int, int, int, int]:
    """返回非白内容的外接框（含 margin，clamp 到图内）。找不到内容则返回整图。"""
    arr = np.asarray(rgb)
    non_white = np.any(arr < thr, axis=2)          # 任一通道低于阈值 = 非白（商品）
    ys, xs = np.where(non_white)
    if ys.size == 0:
        return (0, 0, rgb.width, rgb.height)
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    x1 = max(0, x1 - margin); y1 = max(0, y1 - margin)
    x2 = min(rgb.width, x2 + margin); y2 = min(rgb.height, y2 + margin)
    return (x1, y1, x2, y2)


def _pad_square_white(rgb: Image.Image, target: int | None) -> Image.Image:
    w, h = rgb.size
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(rgb, ((side - w) // 2, (side - h) // 2))
    if target:
        canvas = canvas.resize((target, target), Image.LANCZOS)
    return canvas


def process_one(path: Path, out_dir: Path) -> None:
    img = Image.open(str(path))

    # 1) 抠图（去场景背景），不加水印
    img = _mod.ensure_cutout(img)

    # 2) 合成白底
    rgb = _flatten_to_white(img)

    # 3) 最大化裁剪：按近白阈值裁掉商品四周所有可删白色
    bbox = _content_bbox(rgb, WHITE_THRESHOLD, MARGIN_PX)
    rgb = rgb.crop(bbox)

    # 4) 补白成正方形
    out = _pad_square_white(rgb, TARGET_SIZE)

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{path.stem}.jpg"
    out.save(str(dst), quality=JPEG_QUALITY, subsampling=0, optimize=True)
    print(f"  OK  {path.name} -> {dst.name}  (crop {bbox})")


def main() -> None:
    src = Path(SOURCE_DIR)

    print("=" * 60)
    print("步骤 1/2：改名 _N -> _details")
    print("=" * 60)
    rename_details(src, dry_run=RENAME_DRY_RUN)

    if RENAME_DRY_RUN:
        print("\n[预览模式] 未实际改名，跳过抠图。确认后将 RENAME_DRY_RUN 设为 False 再运行。")
        return

    print("\n" + "=" * 60)
    print("步骤 2/2：抠图（不加水印）+ 最大化裁剪为正方形")
    print("=" * 60)

    targets = sorted(
        f for f in src.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS
        and f.stem.lower().endswith("_details")
    )
    if not targets:
        print(f"[WARN] 未找到 *_details 图片：{src}")
        return

    out_dir = Path(OUTPUT_DIR)
    print(f"待处理：{len(targets)} 张 -> {out_dir}")

    if AUTO_CUTOUT:
        _mod._get_session()  # 提前加载抠图模型

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(process_one, f, out_dir): f for f in targets}
        for i, fut in enumerate(as_completed(futs), 1):
            f = futs[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"  x  {f.name} -> {e}")
            else:
                print(f"[{i}/{len(targets)}] {f.name} 完成")

    print(f"\n完成，输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
