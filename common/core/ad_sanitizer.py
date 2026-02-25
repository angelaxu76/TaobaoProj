# common/core/ad_sanitizer.py
import re
from pathlib import Path
from functools import lru_cache
from typing import Iterable, List, Optional

# 默认敏感词文件路径（可改）
DEFAULT_WORDS_PATH = Path(r"D:\TB\Products\config\ad_sensitive_words.txt")

# 内置兜底敏感词
FALLBACK_WORDS = [
    # ==== 绝对化用语 ====
    "国家级", "世界级", "永恒的经典", "经典之作", "绝对", "唯一", "独家", "首个", "第一",
    "绝无仅有", "永不", "完全", "全面", "绝佳", "首屈一指", "必选", "不可替代",
    "无与伦比", "不可超越", "不可复制", "独一无二", "万能", "完美", "百分百",
    "无可比拟", "终极", "100%有效", "终极解决方案", "史无前例", "空前绝后",

    # ==== 极限级别用语 ====
    "顶级", "最佳", "最优", "最先进", "最强", "最高级", "最流行", "最受欢迎",
    "史上最", "空前", "至尊", "极致", "超凡", "超值", "超级", "顶尖", "巅峰",
    "无敌", "王牌", "冠军", "首选", "权威", "专家推荐", "全球领先", "全国领先",
    "极品", "巅峰之作", "领导者", "领导品牌", "顶级享受", "王牌产品",
    "顶级配置", "终极选择", "极至", "顶尖技术", "巅峰品质", "极品享受",
    "热销榜首", "销量冠军", "人气爆款",

    # ==== 虚假承诺类 ====
    "保证", "确保", "承诺", "无条件", "无风险", "无理由", "必退", "包退",
    "包换", "包赔", "不退不换", "保终身", "终身保修", "终身质保", "无效退款",
    "根治", "包治", "彻底治愈", "永不复发", "零副作用", "绝对安全",
    "彻底解决", "永久有效", "一劳永逸", "立竿见影", "立即见效", "马上见效",
    "免费赠送", "免费领取", "免费试用", "免费用", "零成本", "零投入", "不花钱",

    # ==== 数据绝对化 ====
    "0售假投诉", "0缺陷", "0瑕疵", "0投诉", "全网最低", "100%正品",
    "100% 原装", "100%", "100% 原装进口", "零风险", "零瑕疵", "零添加",
    "零失败", "100%成功率", "100%安全", "100%有效", "100%纯净", "100%天然",
    "100%进口", "100%好评", "100%满意", "100%通过率", "100%准确", "100%覆盖",
    "零误差", "零甲醛", "零污染", "零负担", "零残留", "零差评", "零延迟", "零障碍",

    # ==== 医疗效果类 ====
    "治愈", "治疗", "疗效", "疗效最佳", "药到病除", "安全无毒", "无毒副作用",
    "增强免疫力", "提高记忆力", "抗癌", "防癌", "预防疾病", "延年益寿",

    # ==== 权威背书类 ====
    "特供", "专供", "指定用品", "国家机关推荐", "国家免检", "驰名商标",
    "老字号", "领导人推荐", "政府指定", "权威认证", "专家认证", "院士推荐",
    "诺贝尔奖技术", "奥运专用", "世博会指定"
]

# 正则
RE_100 = re.compile(r"\s*100%\s*", flags=re.IGNORECASE)
RE_SPACES = re.compile(r"\s+")


# common/core/ad_sanitizer.py

POSITIVE_MAP = {
    "可回收利用": "环保材质",
    "可回收": "环保材质",
    "回收": "再生环保材质"
}




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
    """去掉100% + 广告法敏感词 + 多余空格 + 正面替换"""
    if not text:
        return ""
    # 1) 去掉 100%
    text = RE_100.sub(" ", text)

    # 2) 去掉敏感词
    words = set(_load_words(words_path))
    if extra_words:
        words.update(extra_words)
    for w in words:
        text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)

    # 3) 正面化替换
    for bad, good in POSITIVE_MAP.items():
        text = text.replace(bad, good)

    # 4) 压缩空格
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

# common/core/ad_sanitizer.py

POSITIVE_MAP = {
    "可回收利用": "环保材质",
    "可回收": "环保材质",
    "回收": "再生环保材质"
}

def sanitize_text(
    text: str,
    words_path: Optional[str] = None,
    extra_words: Optional[Iterable[str]] = None
) -> str:
    """去掉100% + 广告法敏感词 + 多余空格 + 正面替换"""
    if not text:
        return ""
    # 1) 去掉 100%
    text = RE_100.sub(" ", text)

    # 2) 去掉敏感词
    words = set(_load_words(words_path))
    if extra_words:
        words.update(extra_words)
    for w in words:
        text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)

    # 3) 正面化替换
    for bad, good in POSITIVE_MAP.items():
        text = text.replace(bad, good)

    # 4) 压缩空格
    return RE_SPACES.sub(" ", text).strip()
