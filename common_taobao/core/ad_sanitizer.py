# common_taobao/core/ad_sanitizer.py
import re
from pathlib import Path
from functools import lru_cache
from typing import Iterable, List, Optional

# 默认敏感词文件路径（可改）
DEFAULT_WORDS_PATH = Path(r"D:\TB\Products\config\ad_sensitive_words.txt")

# 内置兜底敏感词
FALLBACK_WORDS = [
    "国家级", "世界级", "顶级", "最佳", "绝对", "唯一", "独家", "首个", "第一",
    "最先进", "最优", "最高级", "极致", "至尊", "顶尖", "终极", "空前", "史上最",
    "无敌", "完美", "王牌", "冠军", "首选", "权威", "专家推荐", "全球领先", "全国领先",
    "0售假投诉", "全网最低", "100%正品", "100% 原装", "100%", "100% 原装进口"
]

# 正则
RE_100 = re.compile(r"\s*100%\s*", flags=re.IGNORECASE)
RE_SPACES = re.compile(r"\s+")

@lru_cache(maxsize=1)
def _load_words(words_path: Optional[str] = None) -> List[str]:
    """加载敏感词（带缓存）"""
    path = Path(words_path) if words_path else DEFAULT_WORDS_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        return words
    return FALLBACK_WORDS

def sanitize_text(
    text: str,
    words_path: Optional[str] = None,
    extra_words: Optional[Iterable[str]] = None
) -> str:
    """去掉100% + 广告法敏感词 + 多余空格"""
    if not text:
        return ""
    text = RE_100.sub(" ", text)
    words = set(_load_words(words_path))
    if extra_words:
        words.update(extra_words)
    for w in words:
        text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)
    return RE_SPACES.sub(" ", text).strip()

def sanitize_features(features: Iterable[str], **kwargs) -> List[str]:
    """清理 features 列表并去重"""
    seen, cleaned = set(), []
    for f in features:
        s = sanitize_text(f or "", **kwargs)
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)
    return cleaned
