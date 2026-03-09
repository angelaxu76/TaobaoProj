"""
LinkFox 换模特图质量对比脚本。

路径配置来自 ops/linkfox/_session_config.py，核心逻辑共享自
ops/ai_image/run_compare_faceswap_quality.py。

可调参数（阈值等）在 ops/ai_image/run_compare_faceswap_quality.py 中修改。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_AI_IMAGE = os.path.join(os.path.dirname(_HERE), "ai_image")

sys.path.insert(0, _ROOT)      # project root
sys.path.insert(0, _HERE)      # ops/linkfox/ — 读本目录的 _session_config
from _session_config import FACESWAP_DIR, PERSON_DIR, FACESWAP_BAD_DIR, COMPARE_CSV

sys.path.insert(0, _AI_IMAGE)  # 找到共享实现
from run_compare_faceswap_quality import main  # noqa: E402

if __name__ == "__main__":
    main(
        faceswap_dir=str(FACESWAP_DIR),
        orig_dir=str(PERSON_DIR),
        bad_dir=str(FACESWAP_BAD_DIR),
        report_csv=str(COMPARE_CSV),
    )
