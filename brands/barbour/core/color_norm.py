# brands/barbour/core/color_norm.py
import re

def norm_color(raw: str) -> str:
    """
    把 Olive/Ancient, Olive Ancient, Olive-Ancient 统一成 olive
    组合色只取第一个主色（符合你之前的规则）
    """
    s = (raw or "").strip().lower()
    s = s.replace("&", " ").replace("/", " ").replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    return s.split(" ")[0]
