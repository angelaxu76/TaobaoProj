# common_taobao/core/category_utils.py

def infer_style_category(desc: str) -> str:
    """
    根据商品描述中的关键词推断商品分类
    """
    desc = (desc or "").lower()
    if "boot" in desc:
        return "boots"
    elif "sandal" in desc:
        return "sandal"
    elif "loafer" in desc:
        return "loafers"
    elif "slip-on" in desc or "slip on" in desc:
        return "slip-on"
    else:
        return "casual shoes"  # ✅ 默认兜底值
