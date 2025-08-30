# barbour/core/site_utils.py
# 统一 Barbour 站点名口径：标准名 == config.BARBOUR["LINKS_FILES"] 的键名（全部小写）
from __future__ import annotations
import re
from typing import Optional, Dict
from urllib.parse import urlparse

try:
    from config import BARBOUR
except Exception:
    # 避免导入顺序问题：给个兜底；实际运行时应从 config 导入
    BARBOUR = {"LINKS_FILES": {
        "outdoorandcountry": None,
        "allweathers": None,
        "barbour": None,
        "houseoffraser": None,
        "philipmorris": None,
    }}

# 允许的标准站点名（来自配置键名）
_CANON: Dict[str, str] = {k.lower(): k.lower() for k in BARBOUR["LINKS_FILES"].keys()}

# 常见别名（Excel/日志/人工输入/历史数据里可能出现的写法）
_ALIASES: Dict[str, str] = {
    "outdoor&country": "outdoorandcountry",
    "outdoor and country": "outdoorandcountry",
    "outdoorcountry": "outdoorandcountry",
    "o&c": "outdoorandcountry",
    "all weather": "allweathers",
    "all weathers": "allweathers",
    "house of fraser": "houseoffraser",
    "hof": "houseoffraser",
    "philip morris": "philipmorris",
    "philip morris direct": "philipmorris",
    "pmd": "philipmorris",
}

# 域名 → 标准站点名（用于从 URL 反推出站点）
_DOMAIN_MAP: Dict[str, str] = {
    "outdoorandcountry.co.uk": "outdoorandcountry",
    "allweathers.co.uk": "allweathers",
    "barbour.com": "barbour",
    "houseoffraser.co.uk": "houseoffraser",
    "philipmorrisdirect.co.uk": "philipmorris",
}

_norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.strip().lower()) if s else ""


def canonical_site(name_or_url: Optional[str]) -> Optional[str]:
    """
    将任意写法（甚至URL）统一为标准站点名（小写）。
    找不到则返回 None，不抛错（读流程用）。
    """
    if not name_or_url:
        return None

    # URL 推断
    val = name_or_url.strip()
    if "://" in val or "." in val:
        try:
            host = urlparse(val).hostname or ""
            host = host.lower()
            # 去掉前缀子域名
            parts = host.split(".")
            for i in range(len(parts) - 2):
                candidate = ".".join(parts[i:])
                if candidate in _DOMAIN_MAP:
                    return _DOMAIN_MAP[candidate]
            # 完整匹配
            if host in _DOMAIN_MAP:
                return _DOMAIN_MAP[host]
        except Exception:
            pass  # 不是 URL，当普通字符串处理

    key = _norm(val)
    if key in _ALIASES:
        key = _ALIASES[key]
    return _CANON.get(key)


def assert_site_or_raise(name_or_url: str) -> str:
    """
    写库前的严格校验：必须能归一化为标准名，否则抛异常。
    """
    site = canonical_site(name_or_url)
    if not site:
        raise ValueError(f"Unrecognized site name: {name_or_url!r}")
    return site


def all_sites() -> list[str]:
    """返回标准站点名列表（来自 config 键名）"""
    return sorted(_CANON.keys())


def equals_site(a: str, b: str) -> bool:
    """宽松相等：两端都归一化后再比较"""
    ca, cb = canonical_site(a), canonical_site(b)
    return (ca is not None) and (ca == cb)
