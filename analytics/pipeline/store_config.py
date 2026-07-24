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

_BASE = Path(r"D:\TB\product_analytics\store")

BASE_DIR    = _BASE / ACTIVE_STORE
CATALOG_DIR = BASE_DIR / "input" / "product_info"
METRICS_DIR = BASE_DIR / "input" / "daily_metrics"
EXPORT_DIR  = BASE_DIR / "export"

# ============================================================
# 筛选 sheet 参数（product_export 额外生成的"冷门商品候选"sheet）
# 保留同时满足以下三个条件的商品：
#   1. pay_amount_{days}d <= FILTER_PAY_AMOUNT_MAX（基本无成交）
#   2. visitors_{days}d   <= FILTER_VISITORS_MAX（访问量不高）
#   3. publication_date   早于 FILTER_PUBLICATION_WEEKS 周前（排除新品）
FILTER_PAY_AMOUNT_MAX: float = 0
FILTER_VISITORS_MAX: float = 20
FILTER_PUBLICATION_WEEKS: int = 3
