# config/settings.py
from pathlib import Path

API_KEYS = {
    "DEEPL": "35bb3d6c-c839-49f6-9a8f-7e00aecf24eb",
}

# 按优先级检测 driver 目录：先找共享目录（VMware Shared Folders），再用本地目录。
# 新增虚拟机时只需把 chromedriver.exe 放到共享目录，无需每台机器单独配置。
_DRIVER_DIR_CANDIDATES = [
    Path(r"\\vmware-host\Shared Folders\VMShared\drivers"),
    Path(r"D:\TB\drivers"),
]

def _pick_driver_dir() -> Path:
    for p in _DRIVER_DIR_CANDIDATES:
        try:
            if (p / "chromedriver.exe").exists():
                return p
        except OSError:
            pass  # 网络路径不可达（如 VMware 共享目录认证失败），跳过
    return _DRIVER_DIR_CANDIDATES[-1]   # 找不到时返回最后一个，运行时再报错


_LOCAL_DRIVER_DIR = Path(r"D:\TB\drivers")   # 自动更新只写本机目录，不动 VMware 共享目录


def _auto_update_local_chromedriver(chrome_v: int, old_v: int | None) -> str | None:
    """
    用 Selenium Manager 下载与 Chrome 主版本匹配的 chromedriver，
    复制到 D:\\TB\\drivers\\chromedriver.exe（旧文件备份为 chromedriver_<旧版本>.exe）。
    成功返回新路径，失败返回 None（不影响程序继续运行）。
    """
    import shutil, subprocess, re
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager
        print(f"[settings] 🔄 Chrome v{chrome_v} 无匹配驱动，正在自动下载...")
        src = SeleniumManager().binary_paths(["--browser", "chrome"]).get("driver_path")
        if not src or not Path(src).exists():
            return None
        out = subprocess.check_output([src, "--version"], timeout=5).decode("utf-8", "ignore")
        m = re.search(r"\b(\d+)\b", out)
        if not m or int(m.group(1)) != chrome_v:
            return None

        _LOCAL_DRIVER_DIR.mkdir(parents=True, exist_ok=True)
        dst = _LOCAL_DRIVER_DIR / "chromedriver.exe"
        if dst.exists():
            backup = _LOCAL_DRIVER_DIR / f"chromedriver_{old_v or 'old'}.exe"
            shutil.copy2(dst, backup)
        shutil.copy2(src, dst)
        print(f"[settings] ✅ 已更新本地驱动为 v{chrome_v}: {dst}")
        return str(dst)
    except Exception as e:
        print(f"[settings] ⚠️ 自动下载驱动失败（{e}），继续使用旧驱动")
        return None


def _resolve_chromedriver_path() -> str | None:
    """
    扫描所有候选目录，优先返回与当前 Chrome 版本精确匹配的 chromedriver.exe。
    若无精确匹配，返回第一个找到的（带警告）；全部找不到返回 None。
    """
    import subprocess, re

    def _chrome_major() -> int | None:
        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(root, r"SOFTWARE\Google\Chrome\BLBeacon")
                    ver, _ = winreg.QueryValueEx(key, "version")
                    m = re.match(r"(\d+)", ver)
                    if m:
                        return int(m.group(1))
                except OSError:
                    pass
        except Exception:
            pass
        for exe in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]:
            if Path(exe).exists():
                try:
                    out = subprocess.check_output([exe, "--version"], timeout=5).decode("utf-8", "ignore")
                    m = re.search(r"\b(\d+)\b", out)
                    if m:
                        return int(m.group(1))
                except Exception:
                    pass
        return None

    def _driver_major(path: str) -> int | None:
        try:
            out = subprocess.check_output([path, "--version"], timeout=5).decode("utf-8", "ignore")
            m = re.search(r"\b(\d+)\b", out)
            return int(m.group(1)) if m else None
        except Exception:
            return None

    chrome_v = _chrome_major()
    first_found = None  # (path_str, driver_v) — 无精确匹配时的兜底

    for p in _DRIVER_DIR_CANDIDATES:
        candidate = p / "chromedriver.exe"
        try:
            if candidate.exists():
                driver_v = _driver_major(str(candidate))
                if chrome_v and driver_v and chrome_v == driver_v:
                    return str(candidate)   # 版本精确匹配，直接返回
                if first_found is None:
                    first_found = (str(candidate), driver_v)
        except OSError:
            pass

    # 没有精确匹配：尝试自动下载匹配版本并放入本地 driver 目录
    if chrome_v:
        updated = _auto_update_local_chromedriver(chrome_v, first_found[1] if first_found else None)
        if updated:
            return updated

    # 仍无精确匹配，用第一个找到的（带警告）
    if first_found:
        path, driver_v = first_found
        if chrome_v and driver_v and chrome_v != driver_v:
            print(f"[settings] ⚠️ 未找到匹配 Chrome v{chrome_v} 的驱动；将使用 v{driver_v}: {path}")
        return path

    return None


DRIVER_DIR = _pick_driver_dir()
GLOBAL_CHROMEDRIVER_PATH = _resolve_chromedriver_path()
GLOBAL_GECKODRIVER_PATH = str(DRIVER_DIR / "geckodriver.exe")

DEFAULT_STOCK_COUNT = 3

SETTINGS = {
    # EXCHANGE_RATE 已移至 cfg/price_config.py
    "STOCK_VALUE_MODE": "binary",
    "DEFAULT_STOCK_COUNT": DEFAULT_STOCK_COUNT,
    "DRIVER_DIR": str(DRIVER_DIR),
    "CHROMEDRIVER_PATH": GLOBAL_CHROMEDRIVER_PATH,
    "GECKODRIVER_PATH": GLOBAL_GECKODRIVER_PATH,
}
