import os
import subprocess
from tools import trim_images_in_folder
from config import BARBOUR

# 你可能还导入了 BARBOUR，用于清空目录等操作

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(BARBOUR)

    print("\n🟡 Step: 1️⃣ 生成 barbour 详情页卡片")
    #generate_html_main(brand="barbour", max_workers=5)  # ✅ 正确调用外部模块函数

    print("生成产品详情卡图片")
    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    #convert_html_to_images( BARBOUR["HTML_DIR"], BARBOUR["HTML_IMAGE"],GECKODRIVER_PATH, 10)

    trim_images_in_folder(BARBOUR["HTML_IMAGE"],BARBOUR["HTML_CUTTER"],file_pattern="*.png", tolerance=5)

if __name__ == "__main__":
    main()
