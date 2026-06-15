from pathlib import Path

# ============================================================
# ⬇  切换淘宝店铺时只改这一行
ACTIVE_STORE = "五小剑"
# ACTIVE_STORE = "英国伦敦代购"
# ============================================================

_BASE = Path(r"D:\TB\product_analytics")

BASE_DIR    = _BASE / ACTIVE_STORE
CATALOG_DIR = BASE_DIR / "input" / "product_info"
METRICS_DIR = BASE_DIR / "input" / "daily_metrics"
EXPORT_DIR  = BASE_DIR / "export"
