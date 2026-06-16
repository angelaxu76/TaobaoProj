from pathlib import Path

# ============================================================
# ⬇  切换淘宝店铺时只改这一行
# ACTIVE_STORE = "五小剑"
ACTIVE_STORE = "英国伦敦代购"
# ============================================================

# 从商品标题推断品牌时使用的关键词（大小写不敏感）
# 新增品牌：在此处添加一行即可
BRAND_KEYWORDS: dict[str, list[str]] = {
    "clarks":   ["clarks", "其乐"],
    "camper":   ["camper", "看步"],
    "ecco":     ["ecco", "爱步"],
    "geox":     ["geox", "健乐士"],
    "barbour":  ["barbour"],
}

_BASE = Path(r"D:\TB\product_analytics")

BASE_DIR    = _BASE / ACTIVE_STORE
CATALOG_DIR = BASE_DIR / "input" / "product_info"
METRICS_DIR = BASE_DIR / "input" / "daily_metrics"
EXPORT_DIR  = BASE_DIR / "export"
