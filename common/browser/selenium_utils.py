# common/core/selenium_utils.py
from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path
from typing import Dict, Optional
from cfg.settings import GLOBAL_CHROMEDRIVER_PATH


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions

# 所有脚本共用的 driver 池（内部 key 会带线程 id，避免多线程抢同一个 driver）
_DRIVERS: Dict[str, webdriver.Chrome] = {}
_DRIVERS_LOCK = threading.Lock()

# 环境变量名称（可选覆盖全局 config）
_ENV_DRIVER_KEY = "CHROMEDRIVER_PATH"


def _get_driver_major(driver_path: Path) -> Optional[int]:
    import re, subprocess
    try:
        out = subprocess.check_output([str(driver_path), "--version"], timeout=5).decode("utf-8", "ignore")
        m = re.search(r"\b(\d+)\b", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _get_chrome_major() -> Optional[int]:
    import re, subprocess, winreg
    try:
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(root, r"SOFTWARE\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")
                m = re.match(r"(\d+)\.", version)
                if m:
                    return int(m.group(1))
            except OSError:
                pass
    except Exception:
        pass
    for exe in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        try:
            out = subprocess.check_output([exe, "--version"], stderr=subprocess.STDOUT, timeout=5).decode("utf-8", "ignore")
            m = re.search(r"\b(\d+)\.", out)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return None


def _download_matching_driver() -> Path:
    from webdriver_manager.chrome import ChromeDriverManager
    wdm_path = ChromeDriverManager().install()
    print(f"[selenium_utils] webdriver-manager downloaded ChromeDriver: {wdm_path}")
    return Path(wdm_path)


def _resolve_driver_path() -> Optional[Path]:
    """
    chromedriver 路径来源（稳定、可控）：
    1) settings.py 中的 GLOBAL_CHROMEDRIVER_PATH（主配置）
    2) 环境变量 CHROMEDRIVER_PATH（可选覆盖）
    3) webdriver-manager 自动下载（兜底，仅在上述路径不存在时触发）
    """

    # 1️⃣ 优先使用 settings.py
    if GLOBAL_CHROMEDRIVER_PATH:
        p = Path(GLOBAL_CHROMEDRIVER_PATH)
        if p.is_file():
            chrome_v = _get_chrome_major()
            driver_v = _get_driver_major(p)
            if chrome_v and driver_v and chrome_v != driver_v:
                print(f"[selenium_utils] ⚠️ chromedriver({driver_v}) 与 Chrome({chrome_v})版本不符，用 webdriver-manager 下载匹配版本")
                try:
                    return _download_matching_driver()
                except Exception as e:
                    raise RuntimeError(f"❌ webdriver-manager 下载失败：{e}")
            return p
        # 路径不存在时用 webdriver-manager 下载
        try:
            return _download_matching_driver()
        except Exception as e:
            raise RuntimeError(
                f"❌ settings.py 中的 GLOBAL_CHROMEDRIVER_PATH 不存在：{p}，"
                f"且 webdriver-manager 下载失败：{e}"
            )

    # 2️⃣ 可选：环境变量兜底
    env_path = os.getenv(_ENV_DRIVER_KEY)
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        else:
            raise RuntimeError(
                f"❌ 环境变量 {_ENV_DRIVER_KEY} 指向的 chromedriver 不存在：{env_path}"
            )

    # 都没有就直接失败
    raise RuntimeError(
        "❌ 未配置 chromedriver，请在 cfg/settings.py 中设置 DRIVER_DIR / GLOBAL_CHROMEDRIVER_PATH"
    )


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
    # 内存节省
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-plugins")
    options.add_argument("--js-flags=--max-old-space-size=256")  # 限制每个 Tab 的 V8 堆（HoF 等 Next.js 站点需要更多空间）
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-renderer-backgrounding")

    return options


def get_driver(
    name: str = "default",
    headless: bool = True,
    window_size: str = "1200,2000",
):
    global _DRIVERS

    key = _make_key(name)

    with _DRIVERS_LOCK:
        if key in _DRIVERS:
            return _DRIVERS[key]

        options = _build_chrome_options(
            headless=headless,
            window_size=window_size
        )

        # ⭐ 核心：只从 settings.py / env 取 driver
        driver_path = _resolve_driver_path()

        print(f"🚗 [get_driver] 使用本地 chromedriver: {driver_path} (key={key})")

        service = Service(str(driver_path))
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)   # 防止 driver.get() 无限阻塞（默认 300s）
        driver.set_script_timeout(15)       # 防止 execute_script() 无限阻塞

        _DRIVERS[key] = driver
        return driver



def quit_driver(name: str = "default"):
    """
    关闭【当前线程】的同名 driver，不影响其他线程。
    """
    global _DRIVERS
    key = _make_key(name)

    with _DRIVERS_LOCK:
        driver = _DRIVERS.pop(key, None)

    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


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
