# config/paths.py
from pathlib import Path

BASE_DIR = Path("D:/TB/Products")
DISCOUNT_EXCEL_DIR = Path("D:/TB/DiscountCandidates")
GEI_SHARED_BASE = Path(r"\\vmware-host\Shared Folders\shared")

def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
