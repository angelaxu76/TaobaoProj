# -*- coding: utf-8 -*-
"""
driver_auto.py
自动适配本机 Chrome 主版本，构建 undetected_chromedriver（uc.Chrome）。
- 自动检测 Windows 上的 Chrome 主版本（注册表 / chrome.exe --version）
- 把主版本传给 uc.Chrome(version_main=...) 来拉取匹配的驱动
- 如遇到"only supports Chrome version XXX"的报错，自动清理 uc 缓存后重试
"""

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import undetected_chromedriver as uc
from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
from cfg.settings import GLOBAL_CHROMEDRIVER_PATH

# Serialize uc.Chrome creation to prevent WinError 32 when multiple threads
# try to rename the downloaded chromedriver.exe simultaneously.
_uc_init_lock = threading.Lock()


def _detect_chrome_major_on_windows():
    """检测 Windows 上的 Chrome 主版本号（int），失败返回 None。"""
    # 1) 注册表读取
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(root, r"SOFTWARE\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")  # e.g. "141.0.7390.125"
                m = re.match(r"(\d+)\.", version)
                if m:
                    return int(m.group(1))
            except OSError:
                pass
    except Exception:
        pass

    # 2) 通过 chrome.exe --version
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            try:
                out = subprocess.check_output([exe, "--version"], stderr=subprocess.STDOUT, timeout=5)
                out = out.decode("utf-8", "ignore")  # "Google Chrome 141.0.7390.125"
                m = re.search(r"\b(\d+)\.", out)
                if m:
                    return int(m.group(1))
            except Exception:
                pass

    return None


def _clear_uc_cache():
    """清理 undetected_chromedriver 的缓存，避免驱动版本残留导致不匹配。"""
    candidates = [
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "undetected_chromedriver"),
        os.path.join(os.path.expanduser("~"), ".undetected_chromedriver"),
    ]
    for p in candidates:
        shutil.rmtree(p, ignore_errors=True)


def _get_driver_major(driver_path: str) -> int | None:
    """读取 chromedriver.exe 的主版本号，失败返回 None。"""
    try:
        out = subprocess.check_output([driver_path, "--version"], timeout=5).decode("utf-8", "ignore")
        m = re.search(r"\b(\d+)\b", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


class UcStartTimeout(RuntimeError):
    pass


def _start_uc_with_timeout(kwargs: dict, timeout: float):
    """
    在后台线程里执行 uc.Chrome(**kwargs)，超过 timeout 秒未返回就强杀这次新启动的
    chromedriver / chrome 进程并抛 UcStartTimeout。
    uc.Chrome() 偶发卡死（selenium 与 chromedriver 之间的 HTTP 调用默认无超时），
    而调用方持有 _uc_init_lock，卡死会让所有排队启动浏览器的线程一起永远卡住。
    """
    import psutil

    me = psutil.Process()
    before = {p.pid for p in me.children(recursive=True)}
    result: dict = {}

    def _target():
        try:
            result["driver"] = uc.Chrome(**kwargs)
        except BaseException as e:
            result["error"] = e

    t = threading.Thread(target=_target, daemon=True, name="uc-start")
    t.start()
    t.join(timeout)

    if t.is_alive():
        for p in me.children(recursive=True):
            if p.pid not in before:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
        # 卡住的线程被丢弃（daemon，不阻塞退出）；万一之后又返回了 driver，也让它自行失效
        raise UcStartTimeout(f"uc.Chrome 启动超过 {timeout:.0f}s 未返回，已强杀新启动的浏览器进程")
    if "error" in result:
        raise result["error"]
    return result["driver"]


def build_uc_driver(headless=False, extra_options=None, retries=2, verbose=True, start_timeout=180):
    """
    自动适配本机 Chrome 主版本，构建 uc.Chrome 并返回 driver 实例。

    参数：
      - headless: 是否无头模式（False 时会打开窗口）
      - extra_options: 额外的 Chrome 启动参数（list[str]），例如 ["--disable-gpu"]
      - retries: 失败后（清缓存）最大重试次数
      - verbose: 是否打印调试信息
      - start_timeout: 单次 uc.Chrome() 启动最长等待秒数，超时强杀并重试

    返回：
      - selenium webdriver 实例（undetected_chromedriver.Chrome）
    """
    def _make_options():
        # uc 不允许复用同一个 ChromeOptions 对象，每次尝试都新建
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        # 你可以按需添加固定参数，例如禁用自动化标记等：
        # options.add_argument("--disable-blink-features=AutomationControlled")
        if extra_options:
            for arg in extra_options:
                options.add_argument(arg)
        return options

    major = _detect_chrome_major_on_windows()
    if verbose:
        print(f"🔍 Detected Chrome major version: {major if major else 'UNKNOWN'}")

    # 传入 version_main 可确保拉取兼容的驱动
    kwargs = dict(headless=headless)
    if major:
        kwargs["version_main"] = major

    # 本地 driver 版本与 Chrome 一致才使用；版本不符时让 uc 自动下载匹配版本
    _resolved = Path(GLOBAL_CHROMEDRIVER_PATH) if GLOBAL_CHROMEDRIVER_PATH else None
    if _resolved and _resolved.is_file():
        driver_major = _get_driver_major(str(_resolved))
        if major and driver_major and driver_major != major:
            if verbose:
                print(f"🔄 本地 chromedriver({driver_major}) 与 Chrome({major})版本不符，uc 将自动下载匹配版本")
        else:
            kwargs["driver_executable_path"] = str(_resolved)
            if verbose:
                print(f"🔧 Using chromedriver: {_resolved}")

    last_err = None
    with _uc_init_lock:
        for attempt in range(1, retries + 1):
            try:
                if verbose:
                    print(f"\U0001f697 Creating uc.Chrome (attempt {attempt}/{retries}) with {kwargs} ...")
                driver = _start_uc_with_timeout({**kwargs, "options": _make_options()}, start_timeout)
                if verbose:
                    print("✅ uc.Chrome started successfully.")
                return driver
            except UcStartTimeout as e:
                last_err = e
                print(f"⚠️ {e}，重试 ({attempt}/{retries})")
                time.sleep(3)
            except SessionNotCreatedException as e:
                last_err = e
                if verbose:
                    print(f"⚠️ SessionNotCreatedException: {e}\n🧹 Clearing uc cache and retrying ...")
                _clear_uc_cache()
                time.sleep(1.5)
            except WebDriverException as e:
                last_err = e
                txt = str(e)
                # 典型报错里会包含 "This version of ChromeDriver only supports Chrome version XXX"
                if "only supports Chrome version" in txt or "session not created" in txt:
                    if verbose:
                        print(f"⚠️ Driver version mismatch: {e}\n🧹 Clearing uc cache and retrying ...")
                    _clear_uc_cache()
                    time.sleep(1.5)
                else:
                    # 其他 webdriver 异常直接抛出，避免吞错
                    raise

    raise last_err if last_err else RuntimeError("Failed to start uc.Chrome with auto version match.")
