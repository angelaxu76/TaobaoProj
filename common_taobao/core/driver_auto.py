# -*- coding: utf-8 -*-
"""
driver_auto.py
自动适配本机 Chrome 主版本，构建 undetected_chromedriver（uc.Chrome）。
- 自动检测 Windows 上的 Chrome 主版本（注册表 / chrome.exe --version）
- 把主版本传给 uc.Chrome(version_main=...) 来拉取匹配的驱动
- 如遇到“only supports Chrome version XXX”的报错，自动清理 uc 缓存后重试
"""

import os
import re
import shutil
import subprocess
import time

import undetected_chromedriver as uc
from selenium.common.exceptions import SessionNotCreatedException, WebDriverException


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


def build_uc_driver(headless=False, extra_options=None, retries=2, verbose=True):
    """
    自动适配本机 Chrome 主版本，构建 uc.Chrome 并返回 driver 实例。

    参数：
      - headless: 是否无头模式（False 时会打开窗口）
      - extra_options: 额外的 Chrome 启动参数（list[str]），例如 ["--disable-gpu"]
      - retries: 失败后（清缓存）最大重试次数
      - verbose: 是否打印调试信息

    返回：
      - selenium webdriver 实例（undetected_chromedriver.Chrome）
    """
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    # 你可以按需添加固定参数，例如禁用自动化标记等：
    # options.add_argument("--disable-blink-features=AutomationControlled")

    if extra_options:
        for arg in extra_options:
            options.add_argument(arg)

    major = _detect_chrome_major_on_windows()
    if verbose:
        print(f"🔍 Detected Chrome major version: {major if major else 'UNKNOWN'}")

    # 传入 version_main 可确保拉取兼容的驱动
    kwargs = dict(options=options, headless=headless)
    if major:
        kwargs["version_main"] = major

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            if verbose:
                print(f"🚗 Creating uc.Chrome (attempt {attempt}/{retries}) with {kwargs} ...")
            driver = uc.Chrome(**kwargs)
            if verbose:
                print("✅ uc.Chrome started successfully.")
            return driver
        except SessionNotCreatedException as e:
            last_err = e
            if verbose:
                print(f"⚠️ SessionNotCreatedException: {e}\n🧹 Clearing uc cache and retrying ...")
            _clear_uc_cache()
            time.sleep(1.5)
        except WebDriverException as e:
            last_err = e
            txt = str(e)
            # 典型报错里会包含 “This version of ChromeDriver only supports Chrome version XXX”
            if "only supports Chrome version" in txt or "session not created" in txt:
                if verbose:
                    print(f"⚠️ Driver version mismatch: {e}\n🧹 Clearing uc cache and retrying ...")
                _clear_uc_cache()
                time.sleep(1.5)
            else:
                # 其他 webdriver 异常直接抛出，避免吞错
                raise

    raise last_err if last_err else RuntimeError("Failed to start uc.Chrome with auto version match.")
