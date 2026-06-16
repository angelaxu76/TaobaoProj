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


def _resolve_chromedriver_path() -> str:
    """
    返回可用的 chromedriver.exe 路径（仅做本地静态检测，不触发下载）。
    若本地无匹配 driver，返回兜底路径；实际下载推迟到 selenium_utils.get_driver() 调用时。
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

    # 找到第一个存在的 chromedriver.exe 就返回；版本校验仅作提示，不阻止使用
    for p in _DRIVER_DIR_CANDIDATES:
        candidate = p / "chromedriver.exe"
        try:
            if candidate.exists():
                chrome_v = _chrome_major()
                driver_v = _driver_major(str(candidate))
                if chrome_v and driver_v and chrome_v != driver_v:
                    print(f"[settings] ⚠️ chromedriver({driver_v}) 与 Chrome({chrome_v})版本不符，仍使用: {candidate}")
                return str(candidate)
        except OSError:
            pass

    # 所有候选都找不到，返回 None；实际下载/报错推迟到 get_driver() / build_driver() 调用时
    return None


DRIVER_DIR = _pick_driver_dir()
GLOBAL_CHROMEDRIVER_PATH = _resolve_chromedriver_path()
GLOBAL_GECKODRIVER_PATH = str(DRIVER_DIR / "geckodriver.exe")

DEFAULT_STOCK_COUNT = 10

SETTINGS = {
    # EXCHANGE_RATE 已移至 cfg/price_config.py
    "STOCK_VALUE_MODE": "binary",
    "DEFAULT_STOCK_COUNT": DEFAULT_STOCK_COUNT,
    "DRIVER_DIR": str(DRIVER_DIR),
    "CHROMEDRIVER_PATH": GLOBAL_CHROMEDRIVER_PATH,
    "GECKODRIVER_PATH": GLOBAL_GECKODRIVER_PATH,
}
