"""
从下载目录/处理目录中选图、整理、水印，准备发布用图片。

步骤：
  1. 按 Excel 中的商品编码从下载/处理目录复制图片到 publish_ready_dir
  2. 重建每款产品的图片目录结构
  3. 将所有图片汇总到统一的平铺目录（IMAGE_PROCESS）
  4. 对序号 0-9 的图片添加水印

处理完成后可直接运行 image_process_and_html.py 进行后续处理。
"""
import shutil
from pathlib import Path

from common.image.copy_images_by_excel import (
    prepare_images_for_publication,
    rebuild_all_products_images,
    collect_all_images_to_flat_dir,
    watermark_index_0_9_inplace,
)
from cfg.brands.barbour import BARBOUR


def move_person_images(source_dir: str, dest_dir: str, verbose: bool = True) -> int:
    """将 source_dir 各商品子目录中的 _1.jpg 和 _2.jpg（模特图）移动到 dest_dir。

    Args:
        source_dir: need_edit 目录，包含各商品编码子目录
        dest_dir:   目标目录，例如 classify/person
        verbose:    是否打印进度

    Returns:
        移动的文件总数
    """
    src = Path(source_dir)
    dst = Path(dest_dir)
    dst.mkdir(parents=True, exist_ok=True)

    moved = 0
    for img in src.glob("*/*_[12].jpg"):
        shutil.move(str(img), dst / img.name)
        moved += 1

    if verbose:
        print(f"[move_person_images] 共移动 {moved} 张模特图 → {dst}")
    return moved


def main():
    excel_path              = r"D:\TB\Products\barbour\document\publication\barbour_publication_20260409_030741.xlsx"
    downloaded_dir          = r"D:\TB\Products\barbour\images_download"
    processed_dir           = r"D:\TB\Products\barbour\images_dummy"
    publish_ready_dir       = r"D:\TB\Products\barbour\repulibcation\images_selected"
    publish_need_process_dir = r"D:\TB\Products\barbour\repulibcation\need_edit"
    missing_txt_path        = r"D:\TB\Products\barbour\repulibcation\missing_codes.txt"

    ready, need_edit, missing = prepare_images_for_publication(
        excel_path=excel_path,
        downloaded_dir=downloaded_dir,
        processed_dir=processed_dir,
        publish_ready_dir=publish_ready_dir,
        publish_need_process_dir=publish_need_process_dir,
        missing_txt_path=missing_txt_path,
        verbose=True,
    )

    move_person_images(
        source_dir=publish_need_process_dir,
        dest_dir=r"D:\TB\Products\barbour\repulibcation\classify\person",
    )

    target_root = publish_ready_dir

    # rebuild_all_products_images(target_root, verbose=True)

    # collect_all_images_to_flat_dir(
    #     target_root,
    #     BARBOUR["IMAGE_PROCESS"],
    #     verbose=True,
    # )

    # watermark_index_0_9_inplace(
    #     BARBOUR["IMAGE_PROCESS"],
    #     watermark_text="英国哈梅尔百货",
    # )


if __name__ == "__main__":
    main()
