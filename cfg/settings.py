# config/settings.py
from pathlib import Path

API_KEYS = {
    "DEEPL": "35bb3d6c-c839-49f6-9a8f-7e00aecf24eb",
}

# 按优先级检测 driver 目录：先找共享目录（VMware Shared Folders），再用本地目录。
# 新增虚拟机时只需把 chromedriver.exe 放到共享目录，无需每台机器单独配置。
_DRIVER_DIR_CANDIDATES = [
    Path(r"\\vmware-host\Shared Folders\shared"),
    Path(r"E:\shared\VMShared\drivers"),
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

DRIVER_DIR = _pick_driver_dir()
GLOBAL_CHROMEDRIVER_PATH = str(DRIVER_DIR / "chromedriver.exe")
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
