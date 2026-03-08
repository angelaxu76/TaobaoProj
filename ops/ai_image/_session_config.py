"""
AI 图片流水线 — 当前操作品牌配置。

切换品牌时只需修改 BRAND_ROOT，以下所有 run_* 脚本自动同步路径：
  run_ai_face_swap.py
  run_faceswap_retry_loop.py
  run_compare_faceswap_quality.py
  run_check_head_proportion.py
  run_find_unprocessed_faceswap.py
  run_score_faceswap_images.py
  run_ai_image_generate.py
"""
from pathlib import Path

# ============================================================
# 修改这一行即可切换品牌
# ============================================================
BRAND_ROOT = Path(r"D:\ms")
# ============================================================

# 以下是从 BRAND_ROOT 自动推导的标准子路径，一般不需要改动
CODES_EXCEL      = BRAND_ROOT / "codes.xlsx"          # 商品编码列表
PERSON_DIR       = BRAND_ROOT / "person"               # 原始人物图
FACESWAP_DIR     = BRAND_ROOT / "faceswap_output"      # 换脸输出图
FACESWAP_BAD_DIR = BRAND_ROOT / "faceswap_bad"         # 质量差/被剔除图
SCORED_DIR       = BRAND_ROOT / "faceswap_scored"      # 评分分级输出
COMPARE_CSV      = BRAND_ROOT / "faceswap_compare_report.csv"
PROPORTION_CSV   = BRAND_ROOT / "proportion_report.csv"
BAD_PROPORTION   = BRAND_ROOT / "faceswap_bad_proportion"
