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


def main():
    # ══════════════════════════════════════════════════════════════════
    # 图片预处理（按需取消注释，0b 和 0c 选其一）
    # ══════════════════════════════════════════════════════════════════

    # ── Step 0a（可选）：将下载目录中的平铺图片按编码/颜色分组到子目录 ──
    # 处理后：image_download/T073568_GREEN_1.webp -> image_download/T073568_GREEN/T073568_GREEN_1.webp
    # from common.image.group_images_by_code import group_by_strip_seq
    # group_by_strip_seq(MARKSANDSPENCER["IMAGE_DOWNLOAD"], overwrite=True)

    # ── Step 0b【纯白底图用】：webp -> jpg + 补白正方形，不抠图，速度快 ──
    # from helper.image.expand_to_square import process_folder
    # process_folder(
    #     str(MARKSANDSPENCER["IMAGE_DOWNLOAD"]),
    #     str(MARKSANDSPENCER["IMAGE_PROCESS"]),
    #     fill_color=(255, 255, 255),
    #     recursive=True,
    #     quality=90,
    # )

    # ── Step 0c【需抠图时用】：rembg 抠图 + 去白毛边 + 补白正方形 ──
    # 在 IMAGE_DOWNLOAD 平铺文件上运行（单层），输出到 IMAGE_PROCESS
    # 完成后如需分组，对 IMAGE_PROCESS 再执行一次 group_by_strip_seq
    import helper.image.cut_square_white_watermark as _cutmod
    _cutmod.MODEL_NAME           = "birefnet-fashion"   # 服装专用模型（比 general 更准）
    _cutmod.AUTO_CUTOUT          = True
    _cutmod.WHITE_BG_SKIP        = True                 # 检测到白底则跳过，节省时间
    _cutmod.TARGET_SIZE          = 1500
    _cutmod.DEFRINGE_WHITE       = True
    _cutmod.ALPHA_ERODE          = 1
    _cutmod.DIAGONAL_TEXT_ENABLE = False                # 此阶段不加水印
    _cutmod.LOCAL_LOGO_ENABLE    = False
    _cutmod.batch_process(
        str(MARKSANDSPENCER["IMAGE_DOWNLOAD"]),
        str(MARKSANDSPENCER["IMAGE_PROCESS"]),
        max_workers=4,
    )

    # ══════════════════════════════════════════════════════════════════

    # excel_path               = r"D:\TB\Products\marksandspencer\repulibcation\publication_excels_outerwear\marksandspencer_男装_外套.xlsx"
    # downloaded_dir           = str(MARKSANDSPENCER["IMAGE_DOWNLOAD"])
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

    target_root = publish_ready_dir

    # rebuild_all_products_images(target_root, verbose=True)

    # collect_all_images_to_flat_dir(
    #     target_root,
    #     MARKSANDSPENCER["IMAGE_PROCESS"],
    #     verbose=True,
    # )

    # watermark_index_0_9_inplace(
    #     MARKSANDSPENCER["IMAGE_PROCESS"],
    #     watermark_text="英国哈梅尔百货",
    # )


if __name__ == "__main__":
    main()
