"""
批量图片后处理入口脚本。

调用 helper/image/cut_square_white_watermark.py 完成：
  - 自动抠图（rembg birefnet-general）
  - 按 alpha 精裁 → 正方形白底居中
  - 斜纹水印 + 右下角小字水印
  - 输出 JPG（可选透明 PNG）

此脚本专注于"本次运行参数"，稳定配置（水印文字、字体、颜色等）
在 helper/image/cut_square_white_watermark.py 中修改。

用法：
  python ops/ai_image/run_cut_square_watermark.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 输入目录（待处理的原始图片）
INPUT_DIR  = r"D:\TB\Products\barbour\facewap\test"

# 输出目录（处理后的 JPG；不存在时自动创建）
OUTPUT_DIR = r"D:\TB\Products\barbour\facewap\faceswap_processed"

# 并发线程数
# birefnet 推理 CPU 密集；AUTO_CUTOUT=True 时建议 ≤ 4，关抠图可调高
MAX_WORKERS = 7

# 是否自动抠图（False = 只做裁正方形 + 水印，跳过 rembg，速度极快）
AUTO_CUTOUT = True

# 是否跳过已是白底的图（True = 检测到白底不调用 rembg，节省时间）
WHITE_BG_SKIP = True

# 输出统一边长（px）；None = 不缩放，保持裁剪后的原始尺寸
TARGET_SIZE = 1500

# ============================================================

import helper.image.cut_square_white_watermark as _mod

# 将本脚本的运行参数注入到模块全局变量
_mod.AUTO_CUTOUT   = AUTO_CUTOUT
_mod.WHITE_BG_SKIP = WHITE_BG_SKIP
_mod.TARGET_SIZE   = TARGET_SIZE

if __name__ == "__main__":
    _mod.batch_process(INPUT_DIR, OUTPUT_DIR, max_workers=MAX_WORKERS)
