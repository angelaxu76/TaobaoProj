"""
Clarks 商品图流水线 — step 1：下载图片。

原来的 image_pipeline_runner.py 拆成了 4 个脚本，这是第 1 步，只负责下载，
不做抖动/翻转（不再用 batch_process_images，改用 AI 生成新视角图代替）、
不裁剪、也不改编号——因为下载完之后你需要先手动去 IMAGE_DOWNLOAD 里删掉
不需要的模特图/生活场景图，删完再重命名才对，所以重命名挪到了
image_pipeline_step2_rename_and_upload_to_r2.py 里，跟上传一起做。

后续步骤：
  1. 打开 CLARKS["IMAGE_DOWNLOAD"]，手动删掉不需要的模特图
  2. image_pipeline_step2_rename_and_upload_to_r2.py —— 按新顺序重命名 + 上传 R2
  3. image_pipeline_step2_ai_rotate.py —— AI 视角旋转
  4. image_pipeline_step3_crop_merge_and_html.py —— 裁剪 + 合并 + 生成详情页
"""
from brands.clarks.download_product_images import download_images_by_code_file

CODE_FILE_PATH = r"D:\TB\Products\clarks\repulibcation\publication_codes.txt"


def main():
    print("下载指定商品编码的的图片")
    download_images_by_code_file(CODE_FILE_PATH)


if __name__ == "__main__":
    main()
