"""
LinkFox 换模特图 — 找出尚未处理的商品编码。

路径配置来自 ops/linkfox/_session_config.py，核心逻辑共享自
ops/ai_image/run_find_unprocessed_faceswap.py。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_AI_IMAGE = os.path.join(os.path.dirname(_HERE), "ai_image")

sys.path.insert(0, _ROOT)      # project root
sys.path.insert(0, _HERE)      # ops/linkfox/ — 读本目录的 _session_config
from _session_config import PERSON_DIR, FACESWAP_DIR, CODES_EXCEL, SHOT_SUFFIXES

sys.path.insert(0, _AI_IMAGE)  # 找到共享实现
from run_find_unprocessed_faceswap import main  # noqa: E402

if __name__ == "__main__":
    main(
        orig_dir=str(PERSON_DIR),
        faceswap_dir=str(FACESWAP_DIR),
        output_excel=str(CODES_EXCEL),
        shot_suffixes=SHOT_SUFFIXES,
    )
