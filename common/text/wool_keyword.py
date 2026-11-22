"""
羊绒卖点关键词（秋冬重点）：检测 + 保证写入标题。

规则配置在 cfg/taobao_title_keyword_config.py 的 WOOL_KEYWORD_RULES / WOOL_IGNORE_PATTERNS。
- detect_wool_keyword(title, content) -> "羊绒" / ""
- ensure_wool_in_title(title, wool_cn, brand_prefix) -> 保证标题含羊绒词且不超过 60 字节
  （用于服装类等未内置该规则的标题生成器的后处理）
"""
import re

from cfg.taobao_title_keyword_config import WOOL_KEYWORD_RULES, WOOL_IGNORE_PATTERNS

# 其它生成器可能产出的羊毛类中文词，统一替换成羊绒词（长词在前）
_WOOL_CN_VARIANTS = ["美丽诺羊毛", "美利奴羊毛", "羊羔毛", "羔羊毛", "羊毛"]


def detect_wool_keyword(title: str, content: str) -> str:
    text = f"{title or ''} {content or ''}"
    for p in WOOL_IGNORE_PATTERNS:
        text = re.sub(p, " ", text, flags=re.IGNORECASE)
    for cn, patterns in WOOL_KEYWORD_RULES:
        for p in patterns:
            if re.search(rf"(?<![A-Za-z]){p}(?![A-Za-z])", text, flags=re.IGNORECASE):
                return cn
    return ""


def _gbk_len(s: str) -> int:
    return len((s or "").encode("gbk", errors="ignore"))


def _truncate_gbk(s: str, max_bytes: int) -> str:
    out, total = "", 0
    for ch in s:
        n = _gbk_len(ch)
        if total + n > max_bytes:
            break
        out += ch
        total += n
    return out


def ensure_wool_in_title(title: str, wool_cn: str, brand_prefix: str = "", max_bytes: int = 60) -> str:
    """标题里没有 wool_cn 时：先把羊毛类中文词替换掉，仍没有则插到品牌名后面；最后截到 max_bytes。"""
    title = (title or "").strip()
    if not wool_cn or wool_cn in title:
        return title

    for v in _WOOL_CN_VARIANTS:
        if v in title:
            title = title.replace(v, wool_cn, 1)
            title = title.replace(v, "")
            break

    if wool_cn not in title:
        if brand_prefix and title.lower().startswith(brand_prefix.lower()):
            n = len(brand_prefix)
            title = title[:n] + wool_cn + title[n:]
        else:
            title = wool_cn + title

    title = title.replace(wool_cn * 2, wool_cn)
    title = re.sub(r"\s{2,}", " ", title).strip()
    if _gbk_len(title) > max_bytes:
        title = _truncate_gbk(title, max_bytes).rstrip()
    return title
