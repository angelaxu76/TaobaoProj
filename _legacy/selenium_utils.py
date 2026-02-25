# common/selenium_utils.py
from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import Dict, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# 所有脚本共用的 driver 池
_DRIVERS: Dict[str, webdriver.Chrome] = {}

# 环境变量名称（可选覆盖全局 config）
_ENV_DRIVER_KEY = "CHROMEDRIVER_PATH"


def _resolve_driver_path() -> Optional[Path]:
    """
    新增功能但不影响旧脚本。
    按优先级自动检查 chromedriver 路径：
    1) 环境变量 CHROMEDRIVER_PATH
    2) config.py 中的 GLOBAL_CHROMEDRIVER_PATH
    3) 找不到则返回 None → 自动回退到 Selenium Manager
    """

    # 1) 检查环境变量
    env_path = os.getenv(_ENV_DRIVER_KEY)
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 2) 检查 config.GLOBAL_CHROMEDRIVER_PATH
    try:
        from config import GLOBAL_CHROMEDRIVER_PATH  # type: ignore
        if GLOBAL_CHROMEDRIVER_PATH and Path(GLOBAL_CHROMEDRIVER_PATH).is_file():  # type: ignore
            return Path(GLOBAL_CHROMEDRIVER_PATH)  # type: ignore
    except Exception:
        pass

    # 找不到 → 返回 None
    return None


def get_driver(
    name: str = "default",
    headless: bool = True,
    window_size: str = "1200,2000",
):
    """
    保持原函数签名完全一致，不修改任何参数结构。
    所有现有脚本都可无缝继续调用。

    新增：内部自动识别本地 chromedriver，
    若找到则使用本地，不再联网下载 → 彻底解决卡死问题。
    """
    global _DRIVERS

    # 已经存在 → 直接复用
    if name in _DRIVERS:
        return _DRIVERS[name]

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={window_size}")

    # 自动检测本地 driver
    driver_path = _resolve_driver_path()

    if driver_path:
        print(f"🚗 [get_driver] 使用本地 chromedriver: {driver_path}")
        service = Service(str(driver_path))
        driver = webdriver.Chrome(service=service, options=options)
    else:
        print(
            "⚠️ [get_driver] 未检测到本地 chromedriver，"
            "回退 Selenium Manager（可能卡住）"
        )
        driver = webdriver.Chrome(options=options)

    _DRIVERS[name] = driver
    return driver


def quit_driver(name: str = "default"):
    driver = _DRIVERS.pop(name, None)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


def quit_all_drivers():
    global _DRIVERS
    for name, driver in list(_DRIVERS.items()):
        try:
            driver.quit()
        except Exception:
            pass
    _DRIVERS.clear()


@atexit.register
def _cleanup():
    quit_all_drivers()
