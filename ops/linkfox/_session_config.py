"""
LinkFox 流水线 — 当前操作品牌配置。

切换品牌时只需修改 BRAND_ROOT，以下所有 run_* 脚本自动同步路径：
  run_linkfox_faceswap.py
"""
from pathlib import Path

# ============================================================
# 修改这一行即可切换品牌
# ============================================================
BRAND_ROOT = Path(r"D:\ms")
# ============================================================

# 以下是从 BRAND_ROOT 自动推导的标准子路径，一般不需要改动
CODES_EXCEL    = BRAND_ROOT / "codes.xlsx"          # 商品编码列表
LINKFOX_DIR    = BRAND_ROOT / "linkfox_output"      # AI换模特输出图
LINKFOX_BAD    = BRAND_ROOT / "linkfox_bad"         # 质量差/被剔除图
