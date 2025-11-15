import os
import sys
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from PIL import Image

# ========== 可配置参数（默认值，可用命令行覆盖） ==========
HTML_FOLDER = Path(r"D:/TB/HTMLToImage/input")
OUTPUT_FOLDER = Path(r"D:/TB/HTMLToImage/output")

# 从 config.py 读取 GeckoDriver 路径；如未配置则用常见默认
try:
    from config import SETTINGS  # 建议在 SETTINGS 里加 key: "GECKODRIVER_PATH"
    GECKODRIVER_PATH = SETTINGS.get("GECKODRIVER_PATH", r"D:/Software/geckodriver.exe")
except Exception:
    GECKODRIVER_PATH = r"D:/Software/geckodriver.exe"


def trim_white_margins_lr(image_path: Path) -> None:
    """
    仅移除图片左右两侧的纯白整列边距（#FFFFFF），避免误剪白底内容。
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    pixels = img.load()

    def is_white_col(x: int) -> bool:
        for y in range(h):
            if pixels[x, y] != (255, 255, 255):
                return False
        return True

    left = 0
    while left < w and is_white_col(left):
        left += 1

    right = w - 1
    while right >= 0 and is_white_col(right):
        right -= 1

    # 若整张都是白的，直接保存原图
    if left >= right:
        img.save(image_path)
        print(f"[trim] all-white image or no content, kept: {image_path}")
        return

    cropped = img.crop((left, 0, right + 1, h))
    cropped.save(image_path)
    print(f"[trim] saved: {image_path}  (crop L:{left} R:{w-1-right})")


def html_to_full_screenshot(html_path: Path, output_image: Path, geckodriver_path: Optional[str] = None) -> None:
    """
    打开本地 HTML 并截取整页长图到 output_image；随后裁去左右纯白边。
    """
    gecko = geckodriver_path or GECKODRIVER_PATH

    options = Options()
    options.add_argument("--headless")
    service = Service(gecko)

    driver = None
    try:
        driver = webdriver.Firefox(service=service, options=options)

        # 用 file:// 协议打开本地 HTML
        driver.get(f"file:///{html_path.as_posix()}")

        # 简单等待渲染（如有异步内容，可改成 WebDriverWait + 条件）
        time.sleep(2)

        # 截取整页
        output_image.parent.mkdir(parents=True, exist_ok=True)
        driver.get_full_page_screenshot_as_file(str(output_image))
        print(f"[shot] saved: {output_image}")

    finally:
        if driver is not None:
            driver.quit()

    # 剪掉左右纯白边
    trim_white_margins_lr(output_image)


def process_html_folder(html_folder, output_folder, geckodriver_path: Optional[str] = None) -> None:
    html_folder = Path(html_folder)
    output_folder = Path(output_folder)

    output_folder.mkdir(parents=True, exist_ok=True)

    for name in os.listdir(html_folder):
        if not name.lower().endswith(".html"):
            continue
        html_path = html_folder / name
        out_name = f"{html_path.stem}.png"
        output_image = output_folder / out_name

        print(f"[proc] {html_path}")
        html_to_full_screenshot(html_path, output_image, geckodriver_path)



def html_to_image(input_dir: Optional[str] = None, output_dir: Optional[str] = None):
    """
    批量将 HTML 转为截图 PNG。
    可直接在 pipeline 调用：
        html_to_image("D:/TB/HTMLToImage/input", "D:/TB/HTMLToImage/output")

    若未传入参数，则使用默认路径或命令行参数。
    """

    # 优先使用函数参数，其次使用命令行参数，最后使用默认配置
    if input_dir:
        html_dir = Path(input_dir)
    elif len(sys.argv) >= 2:
        html_dir = Path(sys.argv[1])
    else:
        html_dir = HTML_FOLDER

    if output_dir:
        out_dir = Path(output_dir)
    elif len(sys.argv) >= 3:
        out_dir = Path(sys.argv[2])
    else:
        out_dir = OUTPUT_FOLDER

    print(f"[conf] HTML_FOLDER={html_dir}")
    print(f"[conf] OUTPUT_FOLDER={out_dir}")
    print(f"[conf] GECKODRIVER_PATH={GECKODRIVER_PATH}")

    process_html_folder(html_dir, out_dir, GECKODRIVER_PATH)



if __name__ == "__main__":
    html_to_image()
