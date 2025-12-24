# -*- coding: utf-8 -*-
"""
Root config shim (backward compatible)

目的：
- 让旧代码继续: from config import BRAND_CONFIG, SETTINGS ...
- 实际配置来源迁移到 ./config/ 目录下的拆分文件
- 通过 importlib 按路径加载，避免与本文件名 config.py 冲突导致递归 import
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
from types import ModuleType
from typing import Dict, Any


# 项目根目录（本文件所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent

# 拆分配置目录：<root>/config/
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_module_from_path(name: str, path: Path) -> ModuleType:
    """Load a python module from a filesystem path."""
    if not path.exists():
        raise FileNotFoundError(f"[config.py] Missing config file: {path}")

    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"[config.py] Cannot load module spec for: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- load split config modules ----
_paths = _load_module_from_path("cfg_paths", CONFIG_DIR / "paths.py")
_db = _load_module_from_path("cfg_db", CONFIG_DIR / "db_config.py")
_settings = _load_module_from_path("cfg_settings", CONFIG_DIR / "settings.py")
_signature = _load_module_from_path("cfg_signature", CONFIG_DIR / "signature.py")
_size_ranges = _load_module_from_path("cfg_size_ranges", CONFIG_DIR / "size_ranges.py")
_brand_strategy = _load_module_from_path("cfg_brand_strategy", CONFIG_DIR / "brand_strategy.py")
_publish = _load_module_from_path("cfg_publish", CONFIG_DIR / "publish_config.py")
_brand_config = _load_module_from_path("cfg_brand_config", CONFIG_DIR / "brand_config.py")


# ---- re-export: DB ----
PGSQL_CONFIG: Dict[str, Any] = getattr(_db, "PGSQL_CONFIG")

# ---- re-export: paths ----
BASE_DIR = getattr(_paths, "BASE_DIR")
DISCOUNT_EXCEL_DIR = getattr(_paths, "DISCOUNT_EXCEL_DIR")
ensure_all_dirs = getattr(_paths, "ensure_all_dirs")

# ---- re-export: settings ----
API_KEYS: Dict[str, Any] = getattr(_settings, "API_KEYS")
SETTINGS: Dict[str, Any] = getattr(_settings, "SETTINGS")
GLOBAL_CHROMEDRIVER_PATH = getattr(_settings, "GLOBAL_CHROMEDRIVER_PATH")

# ---- re-export: signature ----
SIGN_NAME = getattr(_signature, "SIGN_NAME")
SIGN_TITLE = getattr(_signature, "SIGN_TITLE")
SIGN_IMAGE = getattr(_signature, "SIGN_IMAGE")

# ---- re-export: size ranges ----
SIZE_RANGE_CONFIG: Dict[str, Any] = getattr(_size_ranges, "SIZE_RANGE_CONFIG")

# ---- re-export: brand strategy ----
TAOBAO_STORES = getattr(_brand_strategy, "TAOBAO_STORES")
BRAND_STRATEGY: Dict[str, Any] = getattr(_brand_strategy, "BRAND_STRATEGY")
BRAND_NAME_MAP: Dict[str, Any] = getattr(_brand_strategy, "BRAND_NAME_MAP")
BRAND_DISCOUNT: Dict[str, Any] = getattr(_brand_strategy, "BRAND_DISCOUNT")

# ---- re-export: publish config (V2 constants) ----
EXCEL_CONSTANTS_BASE: Dict[str, Any] = getattr(_publish, "EXCEL_CONSTANTS_BASE")
EXCEL_CONSTANTS_BY_BRAND: Dict[str, Any] = getattr(_publish, "EXCEL_CONSTANTS_BY_BRAND")
PUBLISH_RULES_BASE: Dict[str, Any] = getattr(_publish, "PUBLISH_RULES_BASE")
PUBLISH_RULES_BY_BRAND: Dict[str, Any] = getattr(_publish, "PUBLISH_RULES_BY_BRAND")

# ---- re-export: BRAND_CONFIG ----
BRAND_CONFIG: Dict[str, Any] = getattr(_brand_config, "BRAND_CONFIG")

# 可选：显式导出列表（方便 IDE / 避免 * 导出杂物）
__all__ = [
    "PROJECT_ROOT", "CONFIG_DIR",
    "PGSQL_CONFIG",
    "BASE_DIR", "DISCOUNT_EXCEL_DIR", "ensure_all_dirs",
    "API_KEYS", "SETTINGS", "GLOBAL_CHROMEDRIVER_PATH",
    "SIGN_NAME", "SIGN_TITLE", "SIGN_IMAGE",
    "SIZE_RANGE_CONFIG",
    "TAOBAO_STORES", "BRAND_STRATEGY", "BRAND_NAME_MAP", "BRAND_DISCOUNT",
    "EXCEL_CONSTANTS_BASE", "EXCEL_CONSTANTS_BY_BRAND",
    "PUBLISH_RULES_BASE", "PUBLISH_RULES_BY_BRAND",
    "BRAND_CONFIG",
]
