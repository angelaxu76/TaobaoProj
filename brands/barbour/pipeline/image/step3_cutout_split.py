# -*- coding: utf-8 -*-
"""
Barbour 图片流水线 step3：细节图按抠图难易自动拆分。

classify/detail 里前景占比过高（容易抠坏边缘）的图移到 classify/detail_difficult，
其余留在 classify/detail。

运行：python brands/barbour/pipeline/image/step3_cutout_split.py
结束后：人工复核两个目录，然后跑 step4。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root

from brands.barbour.pipeline.image import image_session as S
from brands.barbour.pipeline.image._common import banner, list_images, manual_checkpoint
from helper.image.classify_cutout_difficulty import split_hard_to_cut


def main() -> None:
    if not list_images(S.DETAIL_DIR):
        sys.exit(f"[停止] classify/detail 为空：{S.DETAIL_DIR}")

    banner(f"细节图按抠图难易拆分（阈值 {S.CUTOUT_HARD_THRESHOLD}）")
    split_hard_to_cut(str(S.DETAIL_DIR), str(S.DETAIL_HARD_DIR),
                      threshold=S.CUTOUT_HARD_THRESHOLD, move=True, dry_run=False)

    manual_checkpoint([
        f"适合抠图   ：{S.DETAIL_DIR}（{len(list_images(S.DETAIL_DIR))} 张）",
        f"不适合抠图 ：{S.DETAIL_HARD_DIR}（{len(list_images(S.DETAIL_HARD_DIR))} 张）",
        "上面列出的'接近阈值'的图建议重点看；判断错的在两个目录之间互相移动即可。",
        "完成后运行 step4_finalize_html.py",
    ])


if __name__ == "__main__":
    main()
