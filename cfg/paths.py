# config/paths.py
from pathlib import Path

BASE_DIR = Path("D:/TB/Products")
DISCOUNT_EXCEL_DIR = Path("D:/TB/DiscountCandidates")
GEI_SHARED_BASE = Path(r"\\vmware-host\Shared Folders\shared")

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
