"""
从下载目录/处理目录中选图、整理、水印，准备发布用图片。

步骤：
  0a. [可选] 按编码文件从数据库查询 URL 并下载图片
  0c. [可选] rembg 抠图 + 去白毛边 + 补白正方形
  1.  将图片按编码分组
  2a. 将需要发布商品的图片复制到 OUTPUT DIR
  2b. 将图片分类为模特图和详情图

使用方式：
  - 修改下方 ══ CONFIG ══ 区域的开关 / 路径，然后直接运行此脚本。
  - 跳过某步骤时将对应 RUN_* 设为 False 即可。
"""

from cfg.brands.marksandspencer import MARKSANDSPENCER

_PUB = MARKSANDSPENCER["BASE"] / "publication"

# ══════════════════════════════════════════════════════════════════
#  CONFIG — 按需修改
#
#  推荐流程：
#    Step 0a  下载图片      → publication/image_download/
#    Step 0c  抠图+补白底   → publication/image_process/
#    Step 2b  分类（有/无人脸）
#               有人脸  →  publication/classify/person/   ← Linkfox 换脸
#               无人脸  →  publication/classify/detail/   ← 保留备用
#
#  所有目录均在 publication/ 下，清空时只需清这一个文件夹。
# ══════════════════════════════════════════════════════════════════

# ── 步骤开关 ──────────────────────────────────────────────────────
RUN_0A_DOWNLOAD = False    # 按编码文件从数据库查询 URL 并下载图片
RUN_0C_CUTOUT   = True    # rembg 抠图 + 去白毛边 + 补白正方形
RUN_1_GROUP     = False    # 将图片按编码分组（新流程不需要）
RUN_2A_SELECT   = False    # 将发布商品图片复制到 OUTPUT DIR（新流程不需要）
RUN_2B_CLASSIFY = True    # 分类模特图（有人脸）/ 详情图（无人脸）

# ── Step 0a：按编码下载 ───────────────────────────────────────────
# 下载目录由 cfg 统一管理：publication/image_download/
CODE_TXT_PATH = str(_PUB / "codes_to_download.txt")

# ── Step 0c：抠图参数 ─────────────────────────────────────────────
CUTOUT_MODEL         = "birefnet-general"    # birefnet-fashion 未缓存时回退到 u2net 质量极差，改用已缓存的 general
CUTOUT_AUTO_CUTOUT   = True
CUTOUT_WHITE_BG_SKIP = True                 # 检测到白底则跳过，节省时间
CUTOUT_TARGET_SIZE   = 1500
CUTOUT_MAX_WORKERS   = 4

# ── Step 1：分组目录（新流程已弃用，保留供临时手动使用） ────────────
GROUP_DIRS = [
    # str(_PUB / "image_process"),
]

# ── Step 2a：选图路径（新流程已弃用） ────────────────────────────
SELECT_EXCEL_PATH        = r""
SELECT_DOWNLOADED_DIR    = str(MARKSANDSPENCER["IMAGE_PROCESS"])
SELECT_PROCESSED_DIR     = str(MARKSANDSPENCER["IMAGE_PROCESS"])
SELECT_READY_DIR         = str(_PUB / "images_selected")
SELECT_NEED_PROCESS_DIR  = str(_PUB / "need_edit")
SELECT_MISSING_TXT_PATH  = str(_PUB / "missing_codes.txt")

# ── Step 2b：分类参数 ─────────────────────────────────────────────
# 输入 = Step 0c 抠图输出目录；输出分两路
CLASSIFY_INPUT_DIR    = str(MARKSANDSPENCER["IMAGE_PROCESS"])
CLASSIFY_PERSON_DIR   = str(_PUB / "classify" / "person")   # 有人脸 → Linkfox 换脸
CLASSIFY_DETAIL_DIR   = str(_PUB / "classify" / "detail")   # 无人脸 → 备用
CLASSIFY_RECURSIVE    = False
CLASSIFY_CONFIDENCE   = 0.4
CLASSIFY_REQUIRE_HEAD = True    # True = 只有检测到头部才算人物图
CLASSIFY_HEAD_CONF    = 0.3     # 头部关键点置信度阈值（降低可减少漏检）

# ══════════════════════════════════════════════════════════════════
#  步骤函数
# ══════════════════════════════════════════════════════════════════

def run_0a_download():
    from brands.marksandspencer.download_product_images import download_images_by_code_file
    download_images_by_code_file(CODE_TXT_PATH)


def run_0c_cutout():
    import helper.image.cut_square_white_watermark as _cutmod
    _cutmod.MODEL_NAME           = CUTOUT_MODEL
    _cutmod.AUTO_CUTOUT          = CUTOUT_AUTO_CUTOUT
    _cutmod.WHITE_BG_SKIP        = CUTOUT_WHITE_BG_SKIP
    _cutmod.TARGET_SIZE          = CUTOUT_TARGET_SIZE
    _cutmod.DEFRINGE_WHITE       = True
    _cutmod.ALPHA_ERODE          = 1
    _cutmod.DIAGONAL_TEXT_ENABLE = False
    _cutmod.LOCAL_LOGO_ENABLE    = False
    _cutmod.batch_process(
        str(MARKSANDSPENCER["IMAGE_DOWNLOAD"]),
        str(MARKSANDSPENCER["IMAGE_PROCESS"]),
        max_workers=CUTOUT_MAX_WORKERS,
    )


def run_1_group():
    from common.image.group_images_by_code import group_by_strip_seq
    for d in GROUP_DIRS:
        group_by_strip_seq(d, overwrite=True)


def run_2a_select():
    from common.image.copy_images_by_excel import prepare_images_for_publication
    prepare_images_for_publication(
        excel_path=SELECT_EXCEL_PATH,
        downloaded_dir=SELECT_DOWNLOADED_DIR,
        processed_dir=SELECT_PROCESSED_DIR,
        publish_ready_dir=SELECT_READY_DIR,
        publish_need_process_dir=SELECT_NEED_PROCESS_DIR,
        missing_txt_path=SELECT_MISSING_TXT_PATH,
        verbose=True,
    )


def run_2b_classify():
    from helper.image.classify_person_images import classify_images
    classify_images(
        input_dir=CLASSIFY_INPUT_DIR,
        person_dir=CLASSIFY_PERSON_DIR,
        detail_dir=CLASSIFY_DETAIL_DIR,
        recursive=CLASSIFY_RECURSIVE,
        require_head=CLASSIFY_REQUIRE_HEAD,
        confidence=CLASSIFY_CONFIDENCE,
        head_confidence=CLASSIFY_HEAD_CONF,
    )


# ══════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════

def main():
    if RUN_0A_DOWNLOAD:
        run_0a_download()
    if RUN_0C_CUTOUT:
        run_0c_cutout()
    if RUN_1_GROUP:
        run_1_group()
    if RUN_2A_SELECT:
        run_2a_select()
    if RUN_2B_CLASSIFY:
        run_2b_classify()


if __name__ == "__main__":
    main()
