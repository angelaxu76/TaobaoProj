"""
Barbour 图片人物分类入口。

将 IMAGE_SELECTED 目录中的图片按是否含人物分发到 IMAGE_PERSON_DIR 和 IMAGE_DETAIL_DIR。
核心逻辑见 helper/image/classify_person_images.py。

IMAGE_PERSON_DIR 中的模特图后续交给 AI 换脸脚本（ops/ai_image/）批量处理；
IMAGE_DETAIL_DIR 中的细节/平铺图无需换脸，直接保留。
换脸完成后，将换脸图 + IMAGE_DETAIL_DIR 中的图手动汇总到 BARBOUR["IMAGE_FINAL"]，
再运行 image_process_and_html.py。

运行：python brands/barbour/pipeline/run_classify_person_images.py
"""
from cfg.brands.barbour import BARBOUR
from helper.image.classify_person_images import classify_images

INPUT_DIR  = BARBOUR["IMAGE_SELECTED"]
PERSON_DIR = BARBOUR["IMAGE_PERSON_DIR"]
DETAIL_DIR = BARBOUR["IMAGE_DETAIL_DIR"]
RECURSIVE       = True
CONFIDENCE      = 0.4
REQUIRE_HEAD    = True   # True = 只有检测到头部才算人物图（仅手/腿的细节图归入 detail）
HEAD_CONFIDENCE = 0.3    # 头部关键点置信度阈值（降低可减少漏检）

if __name__ == "__main__":
    classify_images(
        input_dir=INPUT_DIR,
        person_dir=PERSON_DIR,
        detail_dir=DETAIL_DIR,
        recursive=RECURSIVE,
        require_head=REQUIRE_HEAD,
        confidence=CONFIDENCE,
        head_confidence=HEAD_CONFIDENCE,
    )
