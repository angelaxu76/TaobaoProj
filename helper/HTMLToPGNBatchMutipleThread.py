import os
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from PIL import Image

# === 配置 geckodriver 路径 ===
try:
    from config import SETTINGS  # 建议在 SETTINGS 里加 key: "GECKODRIVER_PATH"
    GECKODRIVER_PATH = SETTINGS.get("GECKODRIVER_PATH", r"D:/Software/geckodriver.exe")
except Exception:
    GECKODRIVER_PATH = r"D:/Software/geckodriver.exe"

# === 每个线程复用一个 Firefox 实例 ===
_thread_local = threading.local()

def _get_driver() -> webdriver.Firefox:
    driver = getattr(_thread_local, "driver", None)
    if driver is not None:
        return driver

    firefox_options = Options()
    firefox_options.add_argument("--headless")
    # 可按需加大/缩小默认窗口，避免过长截图内存压力
    firefox_options.set_preference("layout.css.devPixelsPerPx", "1.0")

    service = Service(GECKODRIVER_PATH)
    driver = webdriver.Firefox(service=service, options=firefox_options)
    driver.set_page_load_timeout(30)  # 避免页面卡死
    _thread_local.driver = driver
    return driver

def _quit_driver():
    driver = getattr(_thread_local, "driver", None)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            _thread_local.driver = None

def trim_image(image_path: str):
    """简单去空白（RGB getbbox 对纯白不理想，如需更精准可换差值法）"""
    try:
        image = Image.open(image_path).convert("RGB")
        bbox = image.getbbox()
        if bbox:
            cropped = image.crop(bbox)
            cropped.save(image_path)
            print(f"[Trimmed] {image_path}", flush=True)
    except Exception as e:
        print(f"[TrimError] {image_path} -> {e}", flush=True)

def html_to_full_screenshot(html_path: str, output_image: str):
    """使用 Selenium 截取 HTML 页面截图（线程内复用 driver）"""
    driver = _get_driver()
    try:
        # 关键修复：用合法的 file:// URI
        uri = Path(html_path).resolve().as_uri()  # e.g. file:///C:/...
        driver.get(uri)
        time.sleep(1.5)  # 给页面/资源一点加载时间，可按需调整
        driver.get_full_page_screenshot_as_file(output_image)
        print(f"[Saved] {output_image}", flush=True)
    except TimeoutException:
        print(f"[Error][Timeout] {html_path}", flush=True)
    except WebDriverException as e:
        print(f"[Error][WebDriver] {html_path} -> {e}", flush=True)
    except Exception as e:
        print(f"[Error] {html_path} -> {e}", flush=True)
    finally:
        trim_image(output_image)

def process_html_file(file: str, html_folder: str, output_folder: str, suffix: str):
    """处理单个 HTML 文件"""
    if not file.endswith(".html"):
        return

    html_path = os.path.join(html_folder, file)
    output_image = os.path.join(output_folder, f"{os.path.splitext(file)[0]}.png")
    thread_name = threading.current_thread().name
    print(f"[Start][{thread_name}] {file}", flush=True)
    html_to_full_screenshot(html_path, output_image)

def convert_html_to_images(input_dir: str, output_dir: str, suffix: str, max_workers: int = 2):
    """
    将 HTML 转换为图片（多线程，线程内复用浏览器）
    :param input_dir: HTML 目录
    :param output_dir: 输出图片目录
    :param suffix: 保留的参数（与原接口一致）
    :param max_workers: 最大并发（建议 2~4）
    """
    os.makedirs(output_dir, exist_ok=True)

    html_files = [f for f in os.listdir(input_dir) if f.endswith(".html")]
    total = len(html_files)
    print(f"[Info] Found {total} HTML files.", flush=True)

    if total == 0:
        print(f"[Done] Nothing to do. {output_dir}", flush=True)
        return

    # 逐个提交任务，并打印进度
    futures = []
    done_count = 0
    errors = 0

    try:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="HTML2PNG") as executor:
            for file in html_files:
                futures.append(executor.submit(process_html_file, file, input_dir, output_dir, suffix))

            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    errors += 1
                    print(f"[TaskError] {e}", flush=True)
                finally:
                    done_count += 1
                    if done_count % 10 == 0 or done_count == total:
                        print(f"[Progress] {done_count}/{total} done | errors={errors}", flush=True)
    finally:
        # 关闭本线程 driver（主线程）
        _quit_driver()

    print(f"[Done] All screenshots saved to {output_dir}. Total={total}, Errors={errors}", flush=True)

# 如果你还保留了两个调用（详情卡/首页卡），建议分别调用 convert_html_to_images 并传小一点的 max_workers：
# convert_html_to_images(DESCRIPTION_HTML_DIR, DESCRIPTION_IMG_DIR, suffix="_desc", max_workers=2)
# convert_html_to_images(HOMEPAGE_HTML_DIR, HOMEPAGE_IMG_DIR, suffix="_home", max_workers=2)
