"""
按发布 Excel 从图片下载库中选图，集中到本批次的发布目录。

步骤：
  1. 按 Excel 中的商品编码，从 BARBOUR["IMAGE_DOWNLOAD"]（长期图片库）
     复制对应编码的图片到 BARBOUR["IMAGE_SELECTED"]
  2. 找不到图片的编码写入 BARBOUR["IMAGE_MISSING_TXT"]

后续接 run_classify_person_images.py，对 IMAGE_SELECTED 做人物/细节分类。
"""
from cfg.brands.barbour import BARBOUR
from common.image.copy_images_by_excel import prepare_images_for_publication


def main():
    excel_path = r"D:\TB\Products\barbour\document\publication\barbour_publication_20260709_053447.xlsx"

    # downloaded_dir 和 processed_dir 传同一个库目录：只要编码在库里就直接算 ready，
    # 不再区分"已处理/待处理"两级（这套区分过去从未真正生效过）。
    ready, _, missing = prepare_images_for_publication(
        excel_path=excel_path,
        downloaded_dir=BARBOUR["IMAGE_DOWNLOAD"],
        processed_dir=BARBOUR["IMAGE_DOWNLOAD"],
        publish_ready_dir=BARBOUR["IMAGE_SELECTED"],
        publish_need_process_dir=BARBOUR["IMAGE_SELECTED"],
        missing_txt_path=BARBOUR["IMAGE_MISSING_TXT"],
        verbose=True,
    )


if __name__ == "__main__":
    main()
