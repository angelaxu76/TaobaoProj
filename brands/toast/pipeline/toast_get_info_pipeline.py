# -*- coding: utf-8 -*-
"""
TOAST 抓取流水线：链接 → TXT → 图片 → 尺码表 → 尺码表图片
"""
from brands.toast.collect_product_links import toast_get_links
from brands.toast.fetch_product_info import toast_fetch_all
from brands.toast.download_product_images import download_toast_images
from brands.toast.fetch_size_charts import toast_fetch_size_charts
from brands.toast.pipeline.tool_sizechart_to_image import toast_sizechart_to_image

RUN_COLLECT_LINKS = True
RUN_FETCH_INFO = True
RUN_DOWNLOAD_IMAGES = True
RUN_SIZE_CHARTS = True
RUN_SIZE_CHART_IMAGES = True


def main():
    if RUN_COLLECT_LINKS:
        print("\n🟡 Step 1️⃣ 抓取商品链接")
        toast_get_links()

    if RUN_FETCH_INFO:
        print("\n🟡 Step 2️⃣ 抓取商品信息写入 TXT")
        toast_fetch_all()

    if RUN_DOWNLOAD_IMAGES:
        print("\n🟡 Step 3️⃣ 下载商品图片")
        download_toast_images()

    if RUN_SIZE_CHARTS:
        print("\n🟡 Step 4️⃣ 抓取尺码表 → json + html")
        toast_fetch_size_charts()

    if RUN_SIZE_CHART_IMAGES:
        print("\n🟡 Step 5️⃣ 尺码表 html → 图片")
        toast_sizechart_to_image()


if __name__ == "__main__":
    main()
