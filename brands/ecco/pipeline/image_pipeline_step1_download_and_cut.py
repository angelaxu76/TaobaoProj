"""
ECCO 商品图流水线 — step 1：下载 + 最大化裁剪转 JPG + 改编号后缀。

原来的 image_pipeline_runner.py 已拆成 3 步，这是第 1 步。跑完这一步之后，
建议先打开 ECCO["IMAGE_CUTTER"] 人工看一眼裁剪结果，确认没问题再跑
image_pipeline_step2_upload_to_r2.py。

后续步骤：
  step2 上传: image_pipeline_step2_upload_to_r2.py
  step2 AI旋转: image_pipeline_step2_ai_rotate.py
  step3 合并/生成详情页: image_pipeline_step3_merge_and_html.py
"""
from brands.ecco.helpers_local.image_max_cutter import batch_convert_webp_to_jpg, process_images_in_folder
from brands.ecco.helpers_local.rename_suffix import rename_views_to_numbered_suffix
from brands.ecco.download_product_images_v2 import download_images_by_code_file
from config import ECCO

CODE_FILE_PATH = r"D:\TB\Products\ecco\repulibcation\publication_codes.txt"


def main():
    print("下载指定商品编码的的图片")
    download_images_by_code_file(CODE_FILE_PATH)

    print("最大化裁剪，转JPG")
    process_images_in_folder(ECCO["IMAGE_DOWNLOAD"], ECCO["IMAGE_CUTTER"])

    batch_convert_webp_to_jpg(ECCO["IMAGE_DOWNLOAD"], ECCO["IMAGE_PROCESS"])

    print("改编号后缀，供上传 R2 / AI 旋转使用")
    rename_views_to_numbered_suffix(ECCO["IMAGE_CUTTER"])


if __name__ == "__main__":
    main()
