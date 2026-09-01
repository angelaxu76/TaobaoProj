# config/paths.py
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path("D:/TB/Products")
DISCOUNT_EXCEL_DIR = Path("D:/TB/DiscountCandidates")

# ===== 共享盘路径双栈解析 =====
# 虚拟机(VM)里跑：走 \\vmware-host\Shared Folders\...
# 本地(宿主机)里跑：上面的 UNC 访问不到，自动切到 E:\shared\...
# 两边目录结构一致：\\vmware-host\Shared Folders\shared\ecco  <->  E:\shared\shared\ecco
VM_SHARED_PREFIX = r"\\vmware-host\Shared Folders"
LOCAL_SHARED_PREFIX = r"E:\shared"


@lru_cache(maxsize=1)
def _vm_shared_accessible() -> bool:
    """检测首选共享盘（VM 内的 UNC 路径）能否访问。结果缓存，整个进程只探一次。"""
    try:
        return os.path.isdir(VM_SHARED_PREFIX)
    except OSError:
        return False


def resolve_shared_path(path) -> str:
    r"""
    把以 VM_SHARED_PREFIX 开头的共享盘路径解析成当前环境可访问的实际路径：
    - 首选 \\vmware-host\Shared Folders\...；能访问就原样返回（VM 内运行）
    - 访问不到就把前缀换成 E:\shared\...（本地运行）
    其它路径原样返回。
    """
    s = str(path)
    norm = s.replace("/", "\\")
    if not norm.startswith(VM_SHARED_PREFIX):
        return s
    if _vm_shared_accessible():
        return s
    rel = norm[len(VM_SHARED_PREFIX):].lstrip("\\")
    return str(Path(LOCAL_SHARED_PREFIX) / rel)


GEI_SHARED_BASE = Path(resolve_shared_path(r"\\vmware-host\Shared Folders\shared"))

# 鲸芽后台导出的渠道产品目录文件（GEI@sales_catalogue_export@...xlsx）存放目录，按品牌分子目录
GEI_EXPORT_BASE = Path(r"E:\shared\GEI_SHARED")

# 当前 Windows 用户目录及常用子目录。换电脑/换用户名后自动跟随系统，
# 不再需要在各脚本里硬编码 C:\Users\<某用户名>。
USER_HOME = Path.home()
DESKTOP_DIR = USER_HOME / "Desktop"
DOWNLOADS_DIR = USER_HOME / "Downloads"
ONEDRIVE_UK_DIR = USER_HOME / "OneDrive" / "CrossBorderDocs_UK"
ONEDRIVE_HK_DIR = USER_HOME / "OneDrive" / "CrossBorderDocs_HK"

def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
