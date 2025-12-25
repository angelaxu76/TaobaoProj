# config/brand_strategy.py

TAOBAO_STORES = ["五小剑", "英国伦敦代购2015"]

BRAND_STRATEGY = {
    "camper": "min_price_times_ratio",
    "ecco": "discount_priority",
    "geox": "discount_priority",
    "clarks_jingya": "discount_priority",
}

BRAND_NAME_MAP = {
    "camper": ("Camper", "看步"),
    "clarks": ("Clarks", "其乐"),
    "clarks_jingya": ("Clarks", "其乐"),
    "geox": ("GEOX", "健乐士"),
    "ecco": ("ECCO", "爱步"),
    "barbour": ("Barbour", "巴伯尔"),
    "birkenstock": ("BIRKENSTOCK", "勃肯"),
    "reiss": ("REISS", ""),
    "ms": ("Marks & Spencer", "马莎"),
}

BRAND_DISCOUNT = {
    "camper": 0.73,
    "geox": 1,
    "clarks_jingya": 1.0,
    "ecco": 0.9,
}
