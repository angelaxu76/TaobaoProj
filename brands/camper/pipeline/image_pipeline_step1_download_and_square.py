"""
Camper 商品图流水线 — step 1：下载 + 变成正方形 + 改编号后缀。

原来的 image_pipeline_runner.py 拆成了 4 个脚本，这是第 1 步。不再调用
image_defender_with_flip.batch_process_images（图抖动+水平翻转的防指纹步骤），
因为现在改用 AI 生成新视角图（image_pipeline_step2_ai_rotate.py）来代替。

IMAGE_PROCESS 原来是 batch_process_images 的输出目录，generate_html_from_codes_files /
generate_first_page_from_codes_files 生成详情页/首页封面图时会读这个目录（按
IMAGE_DES_PRIORITY / IMAGE_FIRST_PRIORITY 配置的 F/C/L/T 字母后缀查找），
不能不填，所以这里改成原样拷贝 IMAGE_DOWNLOAD -> IMAGE_PROCESS（不再做抖动/
翻转），字母后缀不变，两个 HTML 生成函数不用改。

IMAGE_CUTTER（供合并 / 上传 R2 / AI 视角旋转用）在方形化之后，把
{编码}_F/C/L/P/T.jpg 改名成 {编码}_1/2/3/4/5.jpg（固定顺序 F->1,C->2,L->3,
P->4,T->5），跟 IMAGE_PROCESS 是两回事，互不影响。

跑完这一步之后，建议先打开 CAMPER["IMAGE_CUTTER"] 人工看一眼有没有裁错/缺图，
确认没问题再跑 image_pipeline_step2_upload_to_r2.py。

后续步骤：
  step2 上传: image_pipeline_step2_upload_to_r2.py
  step2 AI旋转: image_pipeline_step2_ai_rotate.py
  step3 合并/生成详情页: image_pipeline_step3_merge_and_html.py
"""
import shutil
from pathlib import Path

from brands.camper.download_product_images import download_images_from_codes
from brands.camper.helpers_local.ResizeImage import expand_images_in_folder
from brands.camper.helpers_local.rename_suffix import rename_letter_suffix_to_numbered
from config import CAMPER

CODE_FILE_PATH = r"D:\TB\Products\camper\repulibcation\publication_codes.txt"


def _copy_all_images(src_dir, dst_dir) -> None:
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, dst_dir / f.name)


def main():
    print("下载指定商品编码的的图片")
    download_images_from_codes(CODE_FILE_PATH)

    print("原样拷贝到 IMAGE_PROCESS（供生成详情页/首页封面图使用）")
    _copy_all_images(CAMPER["IMAGE_DOWNLOAD"], CAMPER["IMAGE_PROCESS"])

    print("将图片变成正方形")
    expand_images_in_folder(CAMPER["IMAGE_DOWNLOAD"], CAMPER["IMAGE_CUTTER"])

    print("改编号后缀（F/C/L/P/T -> 1/2/3/4/5），供上传 R2 / AI 旋转使用")
    rename_letter_suffix_to_numbered(CAMPER["IMAGE_CUTTER"])


if __name__ == "__main__":
    main()
