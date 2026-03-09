"""
LinkFox 流水线 — 当前操作品牌配置。

切换品牌/模特时只需修改本文件，以下所有 run_* 脚本自动同步：
  run_linkfox_faceswap.py
"""
from pathlib import Path

# ============================================================
# 1. 品牌根目录（切换品牌改这一行）
# ============================================================
BRAND_ROOT = Path(r"D:\ms")
# ============================================================

# 以下是从 BRAND_ROOT 自动推导的标准子路径，一般不需要改动
CODES_EXCEL    = BRAND_ROOT / "codes.xlsx"          # 商品编码列表
LINKFOX_DIR    = BRAND_ROOT / "linkfox_output"      # AI换模特输出图
LINKFOX_BAD    = BRAND_ROOT / "linkfox_bad"         # 质量差/被剔除图

# ============================================================
# 2. 换模特参数（每次任务按需修改）
# ============================================================

# 原始拍摄图所在 R2 子目录（相对 R2_PUBLIC_PREFIX）
#   "" 表示根目录；"product_front" 表示 r2_prefix/product_front/{code}{suffix}.jpg
R2_SHOT_SUBDIR = "product_front"

# 原始拍摄图后缀列表（每个后缀对应一张原图，均会生成一张换模特图）
#   ["_front_1"]              → 每款只处理 {code}_front_1.jpg
#   ["_front_1", "_front_2"] → 每款处理两张
SHOT_SUFFIXES = ["_front_1"]

# 目标模特头部参考图列表（多个 URL 时按商品顺序轮流分配）
TARGET_MODEL_URLS = [
    "https://test-file-ai.linkfox.com//UPLOAD/example/target-model.png",
    # 可添加更多目标模特图：
    # "https://...",
]

# ============================================================
# 3. 与 ai_image 共享脚本的标准接口别名（无需修改）
# ============================================================

# 原始人物图本地目录（run_compare / run_find_unprocessed 读取原图用）
PERSON_DIR       = BRAND_ROOT / "person"

# 共享脚本使用的标准变量名（别名映射）
FACESWAP_DIR     = LINKFOX_DIR          # 换模特输出目录
FACESWAP_BAD_DIR = LINKFOX_BAD          # 质量差/被剔除图
COMPARE_CSV      = BRAND_ROOT / "linkfox_compare_report.csv"
PROPORTION_CSV   = BRAND_ROOT / "proportion_report.csv"
BAD_PROPORTION   = BRAND_ROOT / "faceswap_bad_proportion"
