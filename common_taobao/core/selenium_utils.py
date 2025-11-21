# common_taobao/selenium_utils.py
# 统一管理 Selenium ChromeDriver，所有品牌共用
from __future__ import annotations

import atexit
from pathlib import Path
from typing import Dict, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


# 全局 driver 池：支持按 name 复用
_DRIVERS: Dict[str, webdriver.Chrome] = {}


def get_driver(
    name: str = "default",
    headless: bool = True,
    window_size: str = "1200,2000",
    chromedriver_path: Optional[str] = None,
) -> webdriver.Chrome:
    """
    统一获取（并缓存）一个 Selenium Chrome driver：
    - name: 逻辑名称（例如 "marksandspencer"、"clarks"），同名共用一个 driver
    - headless: 是否无头
    - window_size: 浏览器窗口大小
    - chromedriver_path:
        * 如果传入路径，就使用指定的 chromedriver.exe
        * 如果为 None，则让 Selenium 自动选择匹配当前 Chrome 的 driver（推荐）
    """
    global _DRIVERS

    if name in _DRIVERS:
        return _DRIVERS[name]

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={window_size}")

    if chromedriver_path:
        # 如需强制用某个 driver，可传入路径
        service = Service(str(chromedriver_path))
        driver = webdriver.Chrome(service=service, options=options)
    else:
        # ✅ 推荐：不指定路径，让 Selenium 自己匹配当前 Chrome 版本
        driver = webdriver.Chrome(options=options)

    _DRIVERS[name] = driver
    return driver


def quit_driver(name: str = "default") -> None:
    """关闭某个命名 driver。"""
    driver = _DRIVERS.pop(name, None)
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


def quit_all_drivers() -> None:
    """关闭所有 driver，进程退出时自动调用。"""
    global _DRIVERS
    for name, driver in list(_DRIVERS.items()):
        try:
            driver.quit()
        except Exception:
            pass
    _DRIVERS.clear()


@atexit.register
def _cleanup_on_exit():
    quit_all_drivers()
