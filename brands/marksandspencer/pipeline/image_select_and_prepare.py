"""
从下载目录/处理目录中选图、整理、水印，准备发布用图片。

步骤：
  1. 按 Excel 中的商品编码从下载/处理目录复制图片到 publish_ready_dir
  2. 重建每款产品的图片目录结构
  3. 将所有图片汇总到统一的平铺目录（IMAGE_PROCESS）
  4. 对序号 0-9 的图片添加水印

处理完成后可直接运行后续 HTML 生成流程。
"""
from common.image.copy_images_by_excel import (
    prepare_images_for_publication,
    rebuild_all_products_images,
    collect_all_images_to_flat_dir,
    watermark_index_0_9_inplace,
)
from cfg.brands.marksandspencer import MARKSANDSPENCER
from helper.image.classify_person_images import classify_images
from common.image.group_images_by_code import group_by_strip_seq




def main():

    # ── Step 0c【需抠图时用】：rembg 抠图 + 去白毛边 + 补白正方形 ──
    # 在 IMAGE_DOWNLOAD 平铺文件上运行（单层），输出到 IMAGE_PROCESS
    # 完成后如需分组，对 IMAGE_PROCESS 再执行一次 group_by_strip_seq
    # import helper.image.cut_square_white_watermark as _cutmod
    # _cutmod.MODEL_NAME           = "birefnet-fashion"   # 服装专用模型（比 general 更准）
    # _cutmod.AUTO_CUTOUT          = False
    # _cutmod.WHITE_BG_SKIP        = True                 # 检测到白底则跳过，节省时间
    # _cutmod.TARGET_SIZE          = 1500
    # _cutmod.DEFRINGE_WHITE       = True
    # _cutmod.ALPHA_ERODE          = 1
    # _cutmod.DIAGONAL_TEXT_ENABLE = False                # 此阶段不加水印
    # _cutmod.LOCAL_LOGO_ENABLE    = False
    # _cutmod.batch_process(
    #     str(MARKSANDSPENCER["IMAGE_DOWNLOAD"]),
    #     str(MARKSANDSPENCER["IMAGE_PROCESS"]),
    #     max_workers=4,
    # )



    # ── Step 1 将图片按编码分组 ──
    # group_by_strip_seq(MARKSANDSPENCER["IMAGE_PROCESS"], overwrite=True)
    group_by_strip_seq(r"D:\TB\Products\marksandspencer\repulibcation\classify\person", overwrite=True)

    # ── Step 2 将需要发布商品的图片copy到OUTPUT DIR 单独处理 ──
    # excel_path               = r"D:\TB\Products\marksandspencer\repulibcation\publication_excels_outerwear\marksandspencer_男装_外套.xlsx"
    # downloaded_dir           = str(MARKSANDSPENCER["IMAGE_PROCESS"])
    # processed_dir            = str(MARKSANDSPENCER["IMAGE_PROCESS"])
    # publish_ready_dir        = str(MARKSANDSPENCER["OUTPUT_DIR"] / "images_selected")
    # publish_need_process_dir = str(MARKSANDSPENCER["OUTPUT_DIR"] / "need_edit")
    # missing_txt_path         = str(MARKSANDSPENCER["OUTPUT_DIR"] / "missing_codes.txt")

    # ready, need_edit, missing = prepare_images_for_publication(
    #     excel_path=excel_path,
    #     downloaded_dir=downloaded_dir,
    #     processed_dir=processed_dir,
    #     publish_ready_dir=publish_ready_dir,
    #     publish_need_process_dir=publish_need_process_dir,
    #     missing_txt_path=missing_txt_path,
    #     verbose=True,
    # )



    # # ── Step 2 将图片分类为模特图和详情图 ──
    # INPUT_DIR  = r"D:\TB\Products\marksandspencer\repulibcation\images_selected"
    # PERSON_DIR = r"D:\TB\Products\marksandspencer\repulibcation\classify\person"
    # DETAIL_DIR = r"D:\TB\Products\marksandspencer\repulibcation\classify\detail"
    # RECURSIVE       = True
    # CONFIDENCE      = 0.4
    # REQUIRE_HEAD    = True   # True = 只有检测到头部才算人物图（仅手/腿的细节图归入 detail）
    # HEAD_CONFIDENCE = 0.3    # 头部关键点置信度阈值（降低可减少漏检）
    # classify_images(
    #     input_dir=INPUT_DIR,
    #     person_dir=PERSON_DIR,
    #     detail_dir=DETAIL_DIR,
    #     recursive=RECURSIVE,
    #     require_head=REQUIRE_HEAD,
    #     confidence=CONFIDENCE,
    #     head_confidence=HEAD_CONFIDENCE,
    # )


if __name__ == "__main__":
    main()
