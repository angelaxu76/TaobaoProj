"""
图片处理 + 产品详情 HTML/图片生成流水线。

前置条件：
  1. image_select_and_prepare.py 已运行完成（IMAGE_SELECTED 已就绪）
  2. run_classify_person_images.py 已运行完成（IMAGE_PERSON_DIR / IMAGE_DETAIL_DIR 已就绪）
  3. AI 换脸脚本（ops/linkfox/）已处理完 IMAGE_PERSON_DIR 中的模特图，
     输出直接落在 BARBOUR["IMAGE_PROCESS"]（即 repulibcation/linkfox_processed，
     等同 BARBOUR["IMAGE_FINAL"]），无需再手动汇总

  注意：IMAGE_PROCESS 及以下产出目录（MERGED_DIR / HTML_* / HTML_CUTTER_*）
  都在 repulibcation/ 下，跟 IMAGE_DOWNLOAD 等长期库分开存放，
  避免和原始下载图混在一起导致误删。

步骤：
  1. 将 IMAGE_PROCESS 中的各款图片横向合并为一张宽图（MERGED_DIR）
  2. 按优先级把 IMAGE_PROCESS 里的图片改名为 __1/__2/...（供选图用，
     generate_html.py / generate_html_FristPage.py 现在按 IMAGE_DES_PRIORITY /
     IMAGE_FIRST_PRIORITY 里的数字索引在改名后的 __N 序列里选图，不再认
     front_1_faceswap 这种原始后缀，这一步不能漏）
  3. 生成产品详情卡 HTML（含首页）
  4. 将 HTML 渲染为图片
  5. 裁剪图片两侧留白
"""
from cfg.brands.barbour import BARBOUR
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from helper.image.rename_by_shot_priority import rename_by_shot_priority


def main():
    code_file_path = r"D:\TB\Products\barbour\repulibcation\codes.txt"

    print("将图片 merge 到一张图片中")
    batch_merge_images(BARBOUR["IMAGE_PROCESS"], BARBOUR["MERGED_DIR"], width=750)

    print("按优先级把 IMAGE_PROCESS 里的图片改名为 __1/__2/...")
    rename_by_shot_priority(BARBOUR["IMAGE_PROCESS"], brand="barbour")

    print("生成产品详情卡 HTML")
    generate_html_from_codes_files("barbour", code_file_path, max_workers=2)
    generate_first_page_from_codes_files("barbour", code_file_path)

    print("生成产品详情卡图片")
    convert_html_to_images(BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"], "", 6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_DES"], BARBOUR["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"], "", 6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"], BARBOUR["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
