# common_taobao/core/selenium_utils.py
from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path
from typing import Dict, Optional

# 优先尝试 undetected_chromedriver，没有的话自动回退到普通 webdriver
try:
    import undetected_chromedriver as uc
    _USE_UC = True
except ImportError:
    _USE_UC = False

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions

# 所有脚本共用的 driver 池（内部 key 会带线程 id，避免多线程抢同一个 driver）
_DRIVERS: Dict[str, webdriver.Chrome] = {}
_DRIVERS_LOCK = threading.Lock()

# 环境变量名称（可选覆盖全局 config）
_ENV_DRIVER_KEY = "CHROMEDRIVER_PATH"


def _resolve_driver_path() -> Optional[Path]:
    """
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


def _make_key(name: str) -> str:
    """
    内部用的 key：带上线程 id，保证每个线程有自己的 driver。
    外部参数 name 不变，所以旧代码全部兼容。
    """
    tid = threading.get_ident()
    return f"{name}__{tid}"


def _build_chrome_options(
    headless: bool,
    window_size: str,
) -> ChromeOptions:
    options = ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={window_size}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # 关图片，加快速度
    options.add_argument("--blink-settings=imagesEnabled=false")

    return options


def get_driver(
    name: str = "default",
    headless: bool = True,
    window_size: str = "1200,2000",
):
    """
    ✅ 保持原函数签名完全一致，不修改任何参数结构。
    所有现有脚本都可无缝继续调用。

    升级点：
    - 多线程安全：同一个 name 在不同线程会拿到不同 driver，互不干扰
    - 优先使用 undetected_chromedriver（如果已安装），更抗封锁
    - 找不到 uc 时，使用本地 chromedriver（环境变量 / GLOBAL_CHROMEDRIVER_PATH）
      再不行才走 Selenium Manager（可能会慢）
    """
    global _DRIVERS

    key = _make_key(name)

    with _DRIVERS_LOCK:
        if key in _DRIVERS:
            return _DRIVERS[key]

        options = _build_chrome_options(headless=headless, window_size=window_size)

        if _USE_UC:
            # ⭐ 使用 undetected_chromedriver，适合有 Cloudflare / 反爬的网站
            print(f"🚗 [get_driver] 使用 undetected_chromedriver (key={key})")
            driver = uc.Chrome(options=options, headless=headless)
        else:
            # 走本地 chromedriver → 避免 Selenium Manager 卡死
            driver_path = _resolve_driver_path()
            if driver_path:
                print(f"🚗 [get_driver] 使用本地 chromedriver: {driver_path} (key={key})")
                service = Service(str(driver_path))
                driver = webdriver.Chrome(service=service, options=options)
            else:
                print(
                    f"⚠️ [get_driver] 未检测到本地 chromedriver，"
                    f"回退 Selenium Manager（可能卡住）(key={key})"
                )
                driver = webdriver.Chrome(options=options)

        _DRIVERS[key] = driver
        return driver


def quit_driver(name: str = "default"):
    """
    保持原接口：按 name 关闭 driver。
    内部会把 【同名 + 不同线程】的所有 driver 都关掉。
    """
    global _DRIVERS
    prefix = f"{name}__"

    with _DRIVERS_LOCK:
        to_close = {k: d for k, d in _DRIVERS.items() if k.startswith(prefix)}
        for k, driver in to_close.items():
            try:
                driver.quit()
            except Exception:
                pass
            _DRIVERS.pop(k, None)


def quit_all_drivers():
    """
    旧接口不变：关闭所有 driver。
    建议每个 pipeline 结束时调用一次。
    """
    global _DRIVERS
    with _DRIVERS_LOCK:
        items = list(_DRIVERS.items())
        _DRIVERS.clear()

    for _, driver in items:
        try:
            driver.quit()
        except Exception:
            pass


@atexit.register
def _cleanup():
    quit_all_drivers()
