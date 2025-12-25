# root config.py (single entry, normal imports, stable for CLI)
from __future__ import annotations

# ========== split configs (normal imports) ==========
from cfg.paths import BASE_DIR, DISCOUNT_EXCEL_DIR, ensure_all_dirs
from cfg.settings import API_KEYS, SETTINGS, GLOBAL_CHROMEDRIVER_PATH
from cfg.db_config import PGSQL_CONFIG
from cfg.publish_config import (
    EXCEL_CONSTANTS_BASE,
    EXCEL_CONSTANTS_BY_BRAND,
    PUBLISH_RULES_BASE,
    PUBLISH_RULES_BY_BRAND,
)

from cfg.size_ranges import SIZE_RANGE_CONFIG
from cfg.brand_config import BRAND_CONFIG

# ========== backward-compatible aliases ==========
CAMPER = BRAND_CONFIG.get("camper")
GEOX = BRAND_CONFIG.get("geox")
ECCO = BRAND_CONFIG.get("ecco")
CLARKS = BRAND_CONFIG.get("clarks")
CLARKS_JINGYA = BRAND_CONFIG.get("clarks_jingya")
BIRKENSTOCK = BRAND_CONFIG.get("birkenstock")
BARBOUR = BRAND_CONFIG.get("barbour")
REISS = BRAND_CONFIG.get("reiss")
MARKSANDSPENCER = BRAND_CONFIG.get("marksandspencer")

from cfg.brand_strategy import (
    TAOBAO_STORES,
    BRAND_STRATEGY,
    BRAND_NAME_MAP,
    BRAND_DISCOUNT,
)

__all__ = [
    "BASE_DIR", "DISCOUNT_EXCEL_DIR", "ensure_all_dirs",
    "API_KEYS", "SETTINGS", "GLOBAL_CHROMEDRIVER_PATH",
    "PGSQL_CONFIG",
    "EXCEL_CONSTANTS_BASE", "EXCEL_CONSTANTS_BY_BRAND",
    "PUBLISH_RULES_BASE", "PUBLISH_RULES_BY_BRAND",
    "BRAND_CONFIG",
    "CAMPER", "GEOX", "ECCO", "CLARKS", "CLARKS_JINGYA",
    "BIRKENSTOCK", "BARBOUR", "REISS", "MARKSANDSPENCER",
    "TAOBAO_STORES", "BRAND_STRATEGY", "BRAND_NAME_MAP", "BRAND_DISCOUNT",
]
