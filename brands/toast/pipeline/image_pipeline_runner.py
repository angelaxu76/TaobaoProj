"""
TOAST 图片 + 详情页流水线（与 camper / clarks 一致）

输入：publication_codes_outerwear.txt（prepare_jingya_listing 里 generate_publication_excels_clothing 生成的待发布编码）

步骤（各步骤可独立开关）：
  1. 按编码下载商品图片（+视频）          → IMAGE_DOWNLOAD / VIDEO_DOWNLOAD
  2. 防指纹扰动（微旋转/裁剪/噪点）       → IMAGE_PROCESS（长方形，供 HTML 使用）
  3. 精确抠图 + 白底正方形（同 barbour 的 run_cut_square_watermark，不加水印）
                                          → IMAGE_CUTTER（正方形，供上架主图使用）
  4. 正方形图复制到 document 长期图库     → IMAGE_DIR（发布 Excel 从这里取图）
  5. 正方形图横向合并                     → MERGED_DIR
  6. 按优先级把 IMAGE_PROCESS 改名为 __1/__2/...（供选图用）
  7. 用长方形图生成详情卡 + 首页 HTML     → HTML_DIR_DES / HTML_DIR_FIRST_PAGE
  8. 详情 HTML → 图片 → 裁边              → HTML_IMAGE_DES → HTML_CUTTER_DES
  9. 首页 HTML → 图片 → 裁边              → HTML_IMAGE_FIRST_PAGE → HTML_CUTTER_FIRST_PAGE
 10. 抓尺码表（json + html，已抓过的跳过）→ SIZE_CHART_DIR（document/size）
 11. 尺码表 html → 图片（已有图片的跳过） → SIZE_CHART_IMAGE_DIR（document/size_image）
"""
from config import TOAST
from brands.toast.download_product_images import download_images_from_codes
from brands.toast.fetch_size_charts import toast_fetch_size_charts
from brands.toast.pipeline.tool_sizechart_to_image import toast_sizechart_to_image
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.image_antifingerprint import batch_process_images
from helper.image.expand_to_square import process_folder as expand_images_to_square
import helper.image.cut_square_white_watermark as cutout
from helper.image.copy_images import copy_images
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from ops.image_rename.rename_by_shot_priority import rename_by_shot_priority

# ── 步骤开关 ──────────────────────────────────────────────────────
RUN_1_DOWNLOAD     = True
RUN_2_PROCESS      = True
RUN_3_SQUARE       = True
RUN_4_COPY_DOC     = True
RUN_5_MERGE        = True
RUN_6_RENAME       = True
RUN_7_HTML         = True
RUN_8_RENDER_DES   = True
RUN_9_RENDER_FIRST = True
RUN_10_SIZE_CHART  = True
RUN_11_SIZE_IMAGE  = True

# ── 参数 ──────────────────────────────────────────────────────────
CODE_FILE = TOAST["OUTPUT_DIR"] / "publication_codes_outerwear.txt"
DOWNLOAD_VIDEOS = True
FLIP = False          # 服装图有文字/印花，默认不水平翻转
AUTO_CUTOUT = True    # True = rembg 精确抠图后放白底正方形；False = 不抠图，只用白底补成正方形
CUTOUT_SIZE = 1500    # 抠图输出边长（px），与 barbour 一致
CUTOUT_WORKERS = 2    # birefnet 推理 CPU 密集，建议 ≤ 4
SQUARE_FILL = (255, 255, 255)   # AUTO_CUTOUT=False 时的填充色（与防指纹加的白边一致）
SQUARE_QUALITY = 90
HTML_WORKERS = 6      # HTML → 图片渲染并发线程数


def main():
    code_file_path = str(CODE_FILE)

    if RUN_1_DOWNLOAD:
        print("下载指定商品编码的图片")
        download_images_from_codes(code_file_path, download_videos=DOWNLOAD_VIDEOS)

    if RUN_2_PROCESS:
        print("图片防指纹扰动")
        batch_process_images(TOAST["IMAGE_DOWNLOAD"], TOAST["IMAGE_PROCESS"], flip=FLIP)

    if RUN_3_SQUARE:
        if AUTO_CUTOUT:
            print("精确抠图 + 白底正方形")
            # 防指纹步骤加了白边，白底检测会误判成已是白底而跳过抠图，必须关闭
            cutout.WHITE_BG_SKIP = False
            cutout.TARGET_SIZE = CUTOUT_SIZE
            # 模块里的水印文字是 M&S 的，toast 不能加
            cutout.batch_process(TOAST["IMAGE_PROCESS"], TOAST["IMAGE_CUTTER"],
                                 max_workers=CUTOUT_WORKERS, add_watermark=False)
        else:
            print("将图片扩展成正方形（白底填充，不裁切）")
            expand_images_to_square(TOAST["IMAGE_PROCESS"], TOAST["IMAGE_CUTTER"],
                                    fill_color=SQUARE_FILL, quality=SQUARE_QUALITY)

    if RUN_4_COPY_DOC:
        print("将正方形图片copy到document目录")
        copy_images(TOAST["IMAGE_CUTTER"], TOAST["IMAGE_DIR"])

    if RUN_5_MERGE:
        print("将图片merge到一张图片中")
        batch_merge_images(TOAST["IMAGE_CUTTER"], TOAST["MERGED_DIR"], width=750)

    if RUN_6_RENAME:
        print("按优先级把 IMAGE_PROCESS 里的图片改名为 __1/__2/...")
        rename_by_shot_priority(TOAST["IMAGE_PROCESS"], brand="toast")

    if RUN_7_HTML:
        print("生成产品详情卡HTML（使用 IMAGE_PROCESS 里的长方形图）")
        generate_html_from_codes_files("toast", code_file_path, max_workers=2)
        generate_first_page_from_codes_files("toast", code_file_path)

    if RUN_8_RENDER_DES:
        print("生成产品详情卡图片")
        convert_html_to_images(TOAST["HTML_DIR_DES"], TOAST["HTML_IMAGE_DES"], "", HTML_WORKERS)
        trim_sides_batch(TOAST["HTML_IMAGE_DES"], TOAST["HTML_CUTTER_DES"])

    if RUN_9_RENDER_FIRST:
        print("生成产品首页图片")
        convert_html_to_images(TOAST["HTML_DIR_FIRST_PAGE"], TOAST["HTML_IMAGE_FIRST_PAGE"], "", HTML_WORKERS)
        trim_sides_batch(TOAST["HTML_IMAGE_FIRST_PAGE"], TOAST["HTML_CUTTER_FIRST_PAGE"])

    if RUN_10_SIZE_CHART:
        print("抓取尺码表 → json + html（已抓过的跳过）")
        toast_fetch_size_charts(codes_file=CODE_FILE)

    if RUN_11_SIZE_IMAGE:
        print("尺码表 html → 图片（已有图片的跳过）")
        toast_sizechart_to_image(codes_file=CODE_FILE)


if __name__ == "__main__":
    main()
