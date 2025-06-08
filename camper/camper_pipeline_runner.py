import shutil
import datetime
from pathlib import Path

from GetProductLink import main as get_links
from Fetch_Images_TXT_EAN import main as get_details
from ResizeImage import main as resize_images
from backup_and_clear_publication import main as backup_publication

def run_pipeline():
    print("\n🟡 Step 1：备份并清空 publication 目录")
    backup_publication()

    print("\n🟡 Step 2：抓取 Camper 商品链接")
    get_links()

    print("\n🟡 Step 3：下载商品详情和图片")
    get_details()

    print("\n🟡 Step 4：压缩处理图片尺寸")
    resize_images()

    print("\n✅ 所有步骤已完成！")

if __name__ == "__main__":
    run_pipeline()
