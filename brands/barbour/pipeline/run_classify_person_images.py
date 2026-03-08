"""
Barbour 图片人物分类入口。

将 need_edit 目录中的图片按是否含人物分发到 classify/person 和 classify/detail。
核心逻辑见 helper/image/classify_person_images.py。

运行：python brands/barbour/pipeline/run_classify_person_images.py
"""
from helper.image.classify_person_images import classify_images

INPUT_DIR  = r"D:\TB\Products\barbour\repulibcation\images_selected"
PERSON_DIR = r"D:\TB\Products\barbour\repulibcation\classify\person"
DETAIL_DIR = r"D:\TB\Products\barbour\repulibcation\classify\detail"
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
