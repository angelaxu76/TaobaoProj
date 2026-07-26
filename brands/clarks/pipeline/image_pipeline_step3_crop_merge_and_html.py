"""
Clarks 商品图流水线 — step 3：裁剪 + 合并图片 + 生成详情页/首页 HTML 和图片。

此时 CLARKS["IMAGE_DOWNLOAD"] 已经是 step1 下载 -> 手动删模特图 -> step2
重命名之后的最终版本。

IMAGE_PROCESS 原来是 batch_process_images（抖动+翻转）的输出目录。
common/publication/generate_html.py 对 clarks 品牌有特殊逻辑：直接在
IMAGE_PROCESS 里按 {编码}_{数字}.jpg 找编号最大的文件当详情页封面图（不是
按 IMAGE_DES_PRIORITY 配置查找）。改用 AI 旋转之后不再有抖动/翻转这一步，
所以这里改成原样拷贝 IMAGE_DOWNLOAD -> IMAGE_PROCESS——拷贝的是 step2
重命名之后的最终文件名，"编号最大的文件"才会跟 step2 定的新顺序
（1,6,2,3,5,4,7,8,9 -> 1,2,3,4,5,6,7,8,9）一致。

IMAGE_CUTTER 用 run_crop_and_expand 从 IMAGE_DOWNLOAD 裁剪，供合并/归档用。
最终合并图片来自两个目录：
  - CLARKS["IMAGE_CUTTER"]   —— 本步骤 run_crop_and_expand 的输出
  - CLARKS["IMAGE_ROTATED"]  —— image_pipeline_step2_ai_rotate.py 的输出
batch_merge_images 支持传入多个输入目录（列表），会把两边同一个商品编码的
图片合并到一起再拼图，不需要手动把两个目录的文件挪到一起。
"""
import shutil
from pathlib import Path

from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.image.copy_images import copy_images
from helper.image.crop_to_square import run_crop_and_expand
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from config import CLARKS

CODE_FILE_PATH = r"D:\TB\Products\clarks\repulibcation\publication_codes.txt"

BG_COLOR = (240, 240, 240)
TOLERANCE = 35
QUALITY = 85


def _copy_all_images(src_dir, dst_dir) -> None:
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        # 跳过 rename_suffix.py 留的 .clarks_rename_done_{code} 隐藏标记文件
        if f.is_file() and not f.name.startswith("."):
            shutil.copy2(f, dst_dir / f.name)


def main():
    print("原样拷贝到 IMAGE_PROCESS（供生成详情页/首页封面图使用）")
    _copy_all_images(CLARKS["IMAGE_DOWNLOAD"], CLARKS["IMAGE_PROCESS"])

    print("最大化灰度裁剪图片")
    run_crop_and_expand(CLARKS["IMAGE_DOWNLOAD"], CLARKS["IMAGE_CUTTER"], BG_COLOR, TOLERANCE, QUALITY)

    print("将处理好的图片copy到document目录")
    copy_images(CLARKS["IMAGE_CUTTER"], CLARKS["IMAGE_DIR"])

    print("将图片merge到一张图片中")
    batch_merge_images([CLARKS["IMAGE_CUTTER"], CLARKS["IMAGE_ROTATED"]], CLARKS["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("clarks", CODE_FILE_PATH)
    generate_first_page_from_codes_files("clarks", CODE_FILE_PATH)

    print("生成产品详情卡图片")
    convert_html_to_images(CLARKS["HTML_DIR_DES"], CLARKS["HTML_IMAGE_DES"], "", 6)
    trim_sides_batch(CLARKS["HTML_IMAGE_DES"], CLARKS["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(CLARKS["HTML_DIR_FIRST_PAGE"], CLARKS["HTML_IMAGE_FIRST_PAGE"], "", 6)
    trim_sides_batch(CLARKS["HTML_IMAGE_FIRST_PAGE"], CLARKS["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
