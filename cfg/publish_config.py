# config/publish_config.py

# Excel 发布用固定字段（通用）
EXCEL_CONSTANTS_BASE = {
    "上市季节": "2025冬季",
    "季节": "四季通用",
    "款式": "休闲",
    "闭合方式": "",
    "跟底款式": "平底",
    "开口深度": "浅口",
    "鞋头款式": "圆头",
    "地区国家": "英国",
    "发货时间": "10",
    "运费模版": "parcelforce",
    "第一计量单位": "1",
    "第二计量单位": "1",
    "销售单位": "双",
    "品名": "鞋",
    "海关款式": "休闲鞋",
    "外底材料": "EVA",
    "内底长度": "27",
}

# 品牌覆盖（先留空，后面你需要再加）
EXCEL_CONSTANTS_BY_BRAND = {
    # "camper": {"外底材料": "橡胶"},
}

# 发布筛选阈值（通用）
PUBLISH_RULES_BASE = {
    "MIN_SIZES": 4,
    "MIN_TOTAL_STOCK": 11,
}

# 品牌发布阈值覆盖（按你 generate_publication_excel.py 里的逻辑先写上）
PUBLISH_RULES_BY_BRAND = {
    "clarks_jingya": {"MIN_TOTAL_STOCK": 11},
    "camper": {"MIN_TOTAL_STOCK": 35},
    "geox": {"MIN_TOTAL_STOCK": 11},
}
