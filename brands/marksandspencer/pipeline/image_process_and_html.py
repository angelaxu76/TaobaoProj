"""
图片处理 + 产品详情 HTML/图片生成流水线（M&S）

前置条件：
  image_select_and_prepare.py 已完成（抠图 + 人脸分类），
  Linkfox 换脸已完成。
  将换脸结果 + 无人脸图（classify/detail）手动汇集到
  IMAGES_DIR（publication/image_final/）后运行本脚本。

步骤（各步骤可独立开关）：
  1. 将 IMAGES_DIR 中的各款图片横向合并为一张宽图（image_merged）
  2. 生成产品详情卡 HTML（html/description）
  3. 生成产品首页 HTML（html/first_page）
  4. 将详情 HTML 渲染为图片（html_image/description）
  5. 裁剪详情图片两侧留白（html_cutter/description）
  6. 将首页 HTML 渲染为图片（html_image/first_page）
  7. 裁剪首页图片两侧留白（html_cutter/first_page）

完整目录结构（均在 publication/ 下）：
  publication/
  ├── image_download/           ← 原图下载
  ├── image_process/            ← 抠图+白底
  ├── classify/person/          ← 有人脸 → Linkfox 换脸
  ├── classify/detail/          ← 无人脸 → 直接用
  ├── image_final/              ← ★ 本脚本输入：换脸图+平铺图汇集于此
  ├── image_merged/             ← Step 1 输出
  ├── html/description/         ← Step 2 输出
  ├── html/first_page/          ← Step 3 输出
  ├── html_image/description/   ← Step 4 输出
  ├── html_image/first_page/    ← Step 6 输出
  ├── html_cutter/description/  ← Step 5 输出（最终详情图）
  └── html_cutter/first_page/   ← Step 7 输出（最终首页图）
"""

from cfg.brands.marksandspencer import MARKSANDSPENCER

# ══════════════════════════════════════════════════════════════════
#  CONFIG — 按需修改
# ══════════════════════════════════════════════════════════════════

# ── 步骤开关 ──────────────────────────────────────────────────────
RUN_1_MERGE        = True   # 图片横向合并
RUN_2_HTML_DES     = True   # 生成详情卡 HTML
RUN_3_HTML_FIRST   = True   # 生成首页 HTML
RUN_4_RENDER_DES   = True   # 渲染详情 HTML → 图片
RUN_5_TRIM_DES     = True   # 裁剪详情图片留白
RUN_6_RENDER_FIRST = True   # 渲染首页 HTML → 图片
RUN_7_TRIM_FIRST   = True   # 裁剪首页图片留白

# ── 路径 ──────────────────────────────────────────────────────────
# 换脸图 + 平铺/无人脸图的汇集目录（本脚本所有步骤的最终图片来源）
IMAGES_DIR   = MARKSANDSPENCER["IMAGE_FINAL"]
# 商品编码列表（每行一个编码，对应 TXT_DIR 下的 TXT 文件）
CODES_TXT    = MARKSANDSPENCER["BASE"] / "publication" / "codes.txt"
HTML_WORKERS = 6   # HTML → 图片渲染并发线程数


# ══════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════

def main():
    from config import BRAND_CONFIG
    from helper.image.merge_product_images import batch_merge_images
    from helper.html.html_to_png_multithread import convert_html_to_images
    from helper.image.trim_sides_batch import trim_sides_batch
    from common.publication.generate_html import generate_html_from_codes_files
    from common.publication.generate_html_FristPage import generate_first_page_from_codes_files

    ms = MARKSANDSPENCER

    # generate_html 函数从 BRAND_CONFIG[brand]["IMAGE_PROCESS"] 读图，
    # 本流程的图源是 IMAGE_FINAL，临时覆盖以复用公共生成函数。
    BRAND_CONFIG["marksandspencer"]["IMAGE_PROCESS"] = IMAGES_DIR

    if RUN_1_MERGE:
        print("── Step 1: 合并图片 →", ms["MERGED_DIR"])
        batch_merge_images(IMAGES_DIR, ms["MERGED_DIR"], width=750)

    if RUN_2_HTML_DES:
        print("── Step 2: 生成详情卡 HTML →", ms["HTML_DIR_DES"])
        generate_html_from_codes_files("marksandspencer", CODES_TXT)

    if RUN_3_HTML_FIRST:
        print("── Step 3: 生成首页 HTML →", ms["HTML_DIR_FIRST_PAGE"])
        generate_first_page_from_codes_files("marksandspencer", CODES_TXT)

    if RUN_4_RENDER_DES:
        print("── Step 4: 渲染详情 HTML →", ms["HTML_IMAGE_DES"])
        convert_html_to_images(ms["HTML_DIR_DES"], ms["HTML_IMAGE_DES"], "", HTML_WORKERS)

    if RUN_5_TRIM_DES:
        print("── Step 5: 裁剪详情图片 →", ms["HTML_CUTTER_DES"])
        trim_sides_batch(ms["HTML_IMAGE_DES"], ms["HTML_CUTTER_DES"])

    if RUN_6_RENDER_FIRST:
        print("── Step 6: 渲染首页 HTML →", ms["HTML_IMAGE_FIRST_PAGE"])
        convert_html_to_images(ms["HTML_DIR_FIRST_PAGE"], ms["HTML_IMAGE_FIRST_PAGE"], "", HTML_WORKERS)

    if RUN_7_TRIM_FIRST:
        print("── Step 7: 裁剪首页图片 →", ms["HTML_CUTTER_FIRST_PAGE"])
        trim_sides_batch(ms["HTML_IMAGE_FIRST_PAGE"], ms["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
