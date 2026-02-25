# -*- coding: utf-8 -*-
"""
通用服装标题生成（非外套类）：Dresses / Skirts / Shirts / Knitwear / Trousers / Tops / Jumpsuits...
接口与现有保持一致：
    generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict
返回:
    {"title_cn": "...", "taobao_title": "..."}  # 控制在 60 GBK 字节内
"""

import re
import random
from config import BRAND_NAME_MAP

# ============== 基础工具 ==============
def _gbk_len(s: str) -> int:
    return len(s.encode("gbk", errors="ignore"))

def _truncate_gbk(s: str, max_bytes: int) -> str:
    out, used = [], 0
    for ch in s:
        l = len(ch.encode("gbk", errors="ignore"))
        if used + l > max_bytes:
            break
        out.append(ch); used += l
    return "".join(out)

def _extract(content: str, field: str) -> str:
    m = re.search(rf"{re.escape(field)}\s*[:：]\s*(.+)", content or "", flags=re.I)
    return m.group(1).strip() if m else ""

def _norm(s: str) -> str:
    return (s or "").strip().lower()

# ============== 词库 ==============
COLOR_MAP = {
    "black":"黑色","white":"白色","red":"红色","navy":"深蓝色","tan":"浅棕色","brown":"棕色",
    "blue":"蓝色","grey":"灰色","gray":"灰色","green":"绿色","olive":"橄榄绿","pink":"粉色",
    "burgundy":"酒红色","beige":"米色","cream":"奶油色","camel":"驼色","mocha":"摩卡色",
    "chocolate":"巧克力色","stone":"石灰色","orange":"橙色","purple":"紫色","plum":"梅子色",
    "taupe":"灰褐色","gold":"金色","silver":"银色","khaki":"卡其色","charcoal":"炭灰",
    "ivory":"象牙白","coffee":"咖色","teal":"蓝绿色",
}

FABRIC_MAP = {
    "cotton":"棉","organic cotton":"有机棉","wool":"羊毛","cashmere":"羊绒","merino":"美丽诺羊毛",
    "silk":"真丝","linen":"亚麻","viscose":"粘胶","polyester":"聚酯","nylon":"尼龙","elastane":"弹力",
    "leather":"皮革","suede":"麂皮","denim":"牛仔","modal":"莫代尔","acetate":"醋酸纤维",
}

# 类目 → 中文名 + 特定关键词池（**不含任何“鞋”的词**）
CATEGORY_MAP = {
    "dresses": ("连衣裙", [
        "显瘦","修身","A字","收腰","优雅","通勤","约会","垂坠","顺滑","不易皱","亲肤","飘带","褶皱","裹身","开衩","高腰","法式",
    ]),
    "skirt": ("半身裙", ["显瘦","高腰","伞摆","鱼尾","包臀","百褶","轻盈","通勤","易打理","垂坠"]),
    "skirts": ("半身裙", ["显瘦","高腰","伞摆","鱼尾","包臀","百褶","轻盈","通勤","易打理","垂坠"]),
    "shirt": ("衬衫", ["通勤","易打理","顺滑","垂坠","亲肤","防皱","百搭","修身","立领","翻领","简约"]),
    "shirts": ("衬衫", ["通勤","易打理","顺滑","垂坠","亲肤","防皱","百搭","修身","立领","翻领","简约"]),
    "blouse": ("衬衫", ["通勤","轻盈","飘带","荷叶边","泡袖","优雅","亲肤","透气"]),
    "blouses": ("衬衫", ["通勤","轻盈","飘带","荷叶边","泡袖","优雅","亲肤","透气"]),
    "knitwear": ("针织衫", ["柔软","亲肤","保暖","不扎","弹力","修身","通勤","百搭"]),
    "jumpers": ("针织衫", ["柔软","亲肤","保暖","不扎","弹力","修身","通勤","百搭"]),
    "sweaters": ("针织衫", ["柔软","亲肤","保暖","不扎","弹力","修身","通勤","百搭"]),
    "cardigans": ("针织开衫", ["柔软","亲肤","不扎","开衫","通勤","百搭","休闲"]),
    "trousers": ("长裤", ["显瘦","直筒","阔腿","高腰","垂坠","顺滑","通勤","修身","易打理"]),
    "pants": ("长裤", ["显瘦","直筒","阔腿","高腰","垂坠","顺滑","通勤","修身","易打理"]),
    "jeans": ("牛仔裤", ["显瘦","直筒","高腰","复古","微弹","耐穿","日常"]),
    "tops": ("上衣", ["通勤","百搭","简约","亲肤","透气","不易皱","修身"]),
    "t shirts": ("T恤", ["亲肤","透气","简约","百搭","不易皱","柔软"]),
    "tees": ("T恤", ["亲肤","透气","简约","百搭","不易皱","柔软"]),
    "jumpsuits": ("连体裤", ["显瘦","一体式","高腰","垂坠","顺滑","通勤","优雅"]),
    "playsuits": ("连体裤", ["显瘦","一体式","高腰","垂坠","顺滑","通勤","优雅"]),
}

FILLER = ["英伦","质感","简洁","新款","高级感","都市","轻奢","百搭"]

# ============== 辅助：中文类目判定（基于 style_category + 兜底关键字） ==============
def _category_cn(style_cat: str, title_en: str, desc: str) -> tuple[str, str]:
    s = _norm(style_cat)
    t = _norm(title_en)
    c = _norm(desc)
    blob = f"{t} {c}"

    # 统一 style_category（去符号）
    s_norm = re.sub(r"[^a-z ]+", "", s)

    if s_norm in CATEGORY_MAP:
        cn, _ = CATEGORY_MAP[s_norm]
        return s_norm, cn

    # 兜底关键字
    if re.search(r"\b(dress|dresses)\b", blob): return "dresses", "连衣裙"
    if re.search(r"\b(skirt|skirts)\b", blob): return "skirts", "半身裙"
    if re.search(r"\b(jumpsuit|playsuit)s?\b", blob): return "jumpsuits", "连体裤"
    if re.search(r"\b(jeans?)\b", blob): return "jeans", "牛仔裤"
    if re.search(r"\b(trousers|pants)\b", blob): return "trousers", "长裤"
    if re.search(r"\b(cardigan|sweater|jumper|knit)\b", blob): return "knitwear", "针织衫"
    if re.search(r"\b(blouse|shirt)s?\b", blob): return "shirts", "衬衫"
    if re.search(r"\b(t-?shirt|tee|top)s?\b", blob): return "t shirts", "T恤"

    return "tops", "上衣"

# ============== 颜色/材质/性别 ==============
def _color_cn(title_en: str, color_field: str) -> str:
    key = _norm(color_field)
    if not key:
        tl = _norm(title_en)
        for k in COLOR_MAP:
            if k in tl:
                key = k; break
    return COLOR_MAP.get(key, "")

def _fabric_cn(material_en: str, blob: str) -> str:
    text = _norm(material_en) or _norm(blob)
    # 按词切分直译
    for token in re.split(r"[ /,|]+", text):
        if token in FABRIC_MAP:
            return FABRIC_MAP[token]
    # 关键词包含
    for k, v in FABRIC_MAP.items():
        if k in text:
            return v
    return ""

def _gender_cn(gender_en: str) -> str:
    g = _norm(gender_en)
    if g.startswith("men"): return "男装"
    if g.startswith("women"): return "女装"
    return "女装"

# ============== 主函数 ==============
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    title_en  = _extract(content, "Product Name")
    material  = _extract(content, "Product Material")
    color_en  = _extract(content, "Product Color")
    gender_en = _extract(content, "Product Gender")
    style_cat = _extract(content, "Style Category")
    desc_full = _extract(content, "Product Description") or ""

    # 类目中文 + 关键词池
    cat_key, cat_cn = _category_cn(style_cat, title_en, desc_full)
    kw_pool = CATEGORY_MAP.get(cat_key, (cat_cn, []))[1]

    # 颜色 / 材质 / 性别
    color_cn  = _color_cn(title_en, color_en)
    fabric_cn = _fabric_cn(material, f"{title_en} {desc_full}")
    gender_cn = _gender_cn(gender_en)

    # 从英文标题里抓一个“系列名/款式名”（去除品牌/通用词）
    style = (title_en or "").strip()
    style = re.sub(r"[-_/]", " ", style)
    low = _norm(style)
    low = re.sub(rf"\b{re.escape(_norm(brand_en))}\b", "", low)
    low = re.sub(rf"\b{re.escape(_norm(brand_key))}\b", "", low)
    # 去掉通用类目词
    for g in ["women","womens","men","mens","dress","dresses","skirt","skirts",
              "shirt","shirts","blouse","blouses","trousers","pants","jeans",
              "top","tops","tshirt","t shirt","tee","tees","jumper","sweater",
              "cardigan","knit","jumpsuit","playsuit"]:
        low = re.sub(rf"\b{g}\b", "", low)
    tokens = [w for w in re.split(r"\s+", low) if w]
    style_name = tokens[0].capitalize() if tokens else "系列"

    # 关键词抽取（去夸张词）
    banned = ["最","唯一","首个","顶级","国家级","世界级"]
    feats = []
    blob = _norm(desc_full)
    # 一些常见服装功能词
    if "stretch" in blob or "elastane" in blob: feats.append("弹力")
    if "wrinkle" in blob or "crease" in blob: feats.append("抗皱")
    if "breath" in blob: feats.append("透气")
    if "soft" in blob or "skin" in blob: feats.append("亲肤")
    if "slim" in blob or "fitted" in blob: feats.append("修身")
    if "relaxed" in blob or "loose" in blob: feats.append("宽松")
    if "lined" in blob: feats.append("有里衬")
    if "pleat" in blob: feats.append("百褶")
    if "wrap" in blob: feats.append("裹身")
    if "slit" in blob or "split" in blob: feats.append("开衩")
    if "high waist" in blob or "high-waist" in blob or "high rise" in blob: feats.append("高腰")

    # 合并：类目关键词池 + 自动特征
    agg = []
    for w in kw_pool + feats:
        if w and not any(b in w for b in banned) and w not in agg:
            agg.append(w)
    random.shuffle(agg)
    feat_str = "".join(agg[:4])  # 最多4个，避免爆长

    # 组装标题（控制在 60 GBK 字节）
    parts = [brand_full, gender_cn, style_name, cat_cn, color_cn, fabric_cn, feat_str]
    title = "".join(x for x in parts if x)

    # 裁剪策略：先去特征→材质→颜色→硬截断
    if _gbk_len(title) > 60 and feat_str: title = title.replace(feat_str, "")
    if _gbk_len(title) > 60 and fabric_cn: title = title.replace(fabric_cn, "")
    if _gbk_len(title) > 60 and color_cn: title = title.replace(color_cn, "")
    if _gbk_len(title) > 60: title = _truncate_gbk(title, 60)

    # 不足则轻微填充
    if _gbk_len(title) < 60:
        avail = 60 - _gbk_len(title)
        random.shuffle(FILLER)
        for w in FILLER:
            if _gbk_len(w) <= avail:
                title += w; avail -= _gbk_len(w)
            else:
                break

    return {"title_cn": title, "taobao_title": title}
