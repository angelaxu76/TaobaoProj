from pathlib import Path

# === 数据库连接配置 ===
PGSQL_CONFIG = {
    "host": "192.168.5.243",
    "port": 5432,
    "user": "postgres",
    "password": "516518",
    "dbname": "taobao_inventory_db"
}

API_KEYS = {
    "DEEPL": "35bb3d6c-c839-49f6-9a8f-7e00aecf24eb"
}

SETTINGS = {
    "EXCHANGE_RATE": 9.7
}

BRAND_STRATEGY = {
    "camper": "min_price_times_ratio",
    "ecco": "discount_priority",          # 如果你已经改 ecco 用策略3
    "geox": "discount_priority",
    "clarks_jingya": "min_price_times_ratio",
}


# === 项目根路径 ===
BASE_DIR = Path("D:/TB/Products")
DISCOUNT_EXCEL_DIR = Path("D:/TB/DiscountCandidates")
TAOBAO_STORES = ["五小剑", "英国伦敦代购2015"]
GLOBAL_CHROMEDRIVER_PATH = r"C:\chromedriver\chromedriver.exe"

def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# ✅ 标准尺码配置（淘宝 SKU 对齐）
SIZE_RANGE_CONFIG = {
    "camper": {
        "男款": ["39", "40", "41", "42", "43", "44", "45", "46"],
        "女款": ["35", "36", "37", "38", "39", "40", "41", "42"],
        "童款": ["20", "21", "22", "23", "24", "25","26", "27", "28","29", "30", "31", "32",  "33", "34", "35", "36", "37", "38"]
    },

    # 后续可在这里加其他品牌，如 clarks, ecco, geox
    "clarks": {
        "女款": [  # FEMALE_RANGE 映射
            "35.5", "36", "37", "37.5", "38", "39", "39.5", "40", "41", "41.5", "42"
        ],
        "男款": [  # MALE_RANGE 映射
            "39", "39.5", "40", "41", "41.5", "42", "42.5", "43", "44", "44.5", "45", "46", "46.5", "47"
        ],
        "童款": []  # Clarks 暂不处理童款时可留空或补上
    },

    "geox": {
        "女款": [  # FEMALE_RANGE 映射
            "35", "36","36.5", "37", "37.5", "38","38.5", "39", "39.5", "40", "41",  "42"
        ],
        "男款": [  # MALE_RANGE 映射
            "39", "40", "41", "41.5", "42", "42.5", "43", "43.5","44", "45", "46"
        ],
        "童款": ["24", "25", "26", "27", "28", "29", "30", "31","32", "33", "34", "35","36", "37","38", "39", "40", "41"]  # Clarks 暂不处理童款时可留空或补上
    },

        # 👉 新增 ECCO
    "ecco": {
        "男款": ["39","40","41","42","43","44","45","46"],
        "女款": ["35","36","37","38","39","40","41","42"],
        "童款": ["27","28","29","30","31","32","33","34","35","36","37","38","39","40"],
    }


}





# === Barbour 品牌路径配置 ===
BARBOUR_BASE = BASE_DIR / "barbour"
BARBOUR = {
    "BRAND": "barbour",
    "BASE": BARBOUR_BASE,
	"IMAGE_FIRST_PRIORITY": ["1", "2", "3", "4"],
    "IMAGE_DES_PRIORITY": ["2", "1", "3", "4"],
    "TXT_DIR": BARBOUR_BASE / "publication" /"barbour" /"TXT",
    "TXT_DIR_ALL": BARBOUR_BASE / "publication" /"TXT",
    "OUTPUT_DIR": BARBOUR_BASE / "repulibcation",
    "STORE_DIR": BARBOUR_BASE / "document" / "store",
    "PUBLICATION_DIR": BARBOUR_BASE / "document" / "publication",
    "IMAGE_DIR": BARBOUR_BASE / "publication" / "images",
    "IMAGE_DOWNLOAD": BARBOUR_BASE / "repulibcation" / "images_download",
    "IMAGE_PROCESS": BARBOUR_BASE / "repulibcation" / "images_process",
    "IMAGE_CUTTER": BARBOUR_BASE / "repulibcation" / "images_cutter",
    "ORG_IMAGE_DIR": BARBOUR_BASE / "repulibcation" / "orgin_images",
    "DEF_IMAGE_DIR": BARBOUR_BASE / "repulibcation" / "DEF_images",
    "MERGED_DIR": BARBOUR_BASE / "repulibcation" / "image_merged",
    "HTML_DIR": BARBOUR_BASE / "repulibcation" / "html",
    "HTML_DIR_DES": BARBOUR_BASE / "repulibcation" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": BARBOUR_BASE / "repulibcation" / "html"/ "first_page",
    "HTML_IMAGE": BARBOUR_BASE / "repulibcation" / "html_image",
    "HTML_IMAGE_DES": BARBOUR_BASE / "repulibcation" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": BARBOUR_BASE / "repulibcation" / "html_image"/"first_page",
    "HTML_CUTTER_DES": BARBOUR_BASE / "repulibcation" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": BARBOUR_BASE / "repulibcation" / "html_cutter"/ "first_page",
    "HTML_DEST": BARBOUR_BASE / "repulibcation" / "dest",
    "TABLE_NAME": "barbour_inventory",
    "TAOBAO_STORE_DISCOUNT": 1,  # 不包关税→淘宝店铺价再打9折
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": BARBOUR_BASE / "publication" / "barbour" / "product_links.txt",
    # === 新增 houseoffraser 配置 ===
    
# === 新增 very 配置 ===
    "LINKS_FILES": {
        "outdoorandcountry": BARBOUR_BASE / "publication" / "outdoorandcountry" / "product_links.txt",
        "allweathers":       BARBOUR_BASE / "publication" / "allweathers" / "product_links.txt",
        "barbour":           BARBOUR_BASE / "publication" / "barbour" / "product_links.txt",
        "houseoffraser":     BARBOUR_BASE / "publication" / "houseoffraser" / "product_links.txt",
        "philipmorris":      BARBOUR_BASE / "publication" / "philipmorris" / "product_links.txt",
        "very":              BARBOUR_BASE / "publication" / "very" / "product_links.txt",
        "terraces":          BARBOUR_BASE / "publication" / "terraces" / "product_links.txt",
        "flannels":          BARBOUR_BASE / "publication" / "flannels" / "product_links.txt",   # ✅ 新增 Flannels
    },


    "SUPPLIER_DISCOUNT_RULES": {
        # O&C / Allweathers：有折扣价就用折扣价，不再额外打折；
        # 没有折扣价时，对原价再打 9 折；运费先按 0 配，有需要再加。
        "outdoorandcountry": {
            "strategy": "ratio_when_no_discount",   # 对应 strategy_ratio_when_no_discount
            "extra_ratio": 0.90,
            "shipping_fee": 0.0,
        },
        "allweathers": {
            "strategy": "all_ratio",
            "extra_ratio": 0.90,
            "shipping_fee": 0.0,
        },

        # Barbour 官网：先简单用“有折扣就再打 extra_ratio”的版本，
        # 如果你之后明确它不叠加就改成 ratio_when_no_discount
        "barbour": {
            "strategy": "all_ratio",                # 对应 strategy_all_ratio
            "extra_ratio": 1.0,                     # 目前不额外打折
            "shipping_fee": 0.0,
        },

        # House of Fraser / Philip Morris / Very / Terraces / Flannels
        # 先默认：有折扣就用折扣价、没折扣就用原价，不额外打折、不加运费
        "houseoffraser": {
            "strategy": "all_ratio",
            "extra_ratio": 1.0,
            "shipping_fee": 0.0,
        },
        "philipmorris": {
            "strategy": "all_ratio",
            "extra_ratio": 0.9,
            "shipping_fee": 0.0,
        },
        "very": {
            "strategy": "ratio_when_no_discount",
            "extra_ratio": 1.0,
            "shipping_fee": 4.0,
        },
        "terraces": {
            "strategy": "ratio_when_no_discount",
            "extra_ratio": 1.0,
            "shipping_fee": 0.0,
        },
        "flannels": {
            "strategy": "ratio_when_no_discount",
            "extra_ratio": 1.0,
            "shipping_fee": 0.0,
        },

        # 默认兜底：任何没单独配的网站都走这里
        "__default__": {
            "strategy": "ratio_when_no_discount",
            "extra_ratio": 1.0,
            "shipping_fee": 0.0,
        },
    },


    "TXT_DIRS": {
        "all":               BARBOUR_BASE / "publication" / "TXT",
        "outdoorandcountry": BARBOUR_BASE / "publication" / "outdoorandcountry" / "TXT",
        "allweathers":       BARBOUR_BASE / "publication" / "allweathers" / "TXT",
        "barbour":           BARBOUR_BASE / "publication" / "barbour" / "TXT",
        "houseoffraser":     BARBOUR_BASE / "publication" / "houseoffraser" / "TXT",
        "philipmorris":      BARBOUR_BASE / "publication" / "philipmorris" / "TXT",
        "very":              BARBOUR_BASE / "publication" / "very" / "TXT",
        "terraces":          BARBOUR_BASE / "publication" / "terraces" / "TXT",
        "flannels":          BARBOUR_BASE / "publication" / "flannels" / "TXT",   # ✅ 新增 Flannels
    },


    "FIELDS": {
        "product_code":   "product_code",
        "url":            "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size":           "size",
        "stock":          "stock_status",
        "gender":         "gender",
    },






    "CODE_PREFIX_RULES":{
        # Wax Jackets
        "MWX": ("男款", "蜡棉夹克"),
        "LWX": ("女款", "蜡棉夹克"),

        # Quilted Jackets
        "MQU": ("男款", "绗缝夹克"),
        "LQU": ("女款", "绗缝夹克"),

        # Casual Jackets
        "MCA": ("男款", "休闲夹克"),
        "LCA": ("女款", "休闲夹克"),

        # Liners
        "MLI": ("男款", "内胆"),
        "LLI": ("女款", "内胆"),

        # Gilets
        "MGL": ("男款", "马甲"),
        "LGL": ("女款", "马甲"),

        # Knitwear
        "MKN": ("男款", "针织"),
        "LKN": ("女款", "针织"),

        # Shirts
        "MSH": ("男款", "衬衫"),
        "LSH": ("女款", "衬衫"),

        # T-Shirts
        "MTS": ("男款", "T恤"),
        "LTS": ("女款", "T恤"),
    },

    "BARBOUR_COLOR_CODE_MAP": {
        # ===== 高频主色 =====
        "BK": {"en": "black",          "zh": "黑色"},
        "NY": {"en": "navy",           "zh": "深蓝"},
        "OL": {"en": "olive",          "zh": "橄榄绿"},
        "WH": {"en": "white",          "zh": "白色"},
        "GN": {"en": "green",          "zh": "绿色"},                 # 有时是 forest / uniform green 一类
        "GY": {"en": "grey",           "zh": "灰色"},
        "BR": {"en": "brown",          "zh": "棕色"},
        "BE": {"en": "beige",          "zh": "米色"},
        "SG": {"en": "sage",           "zh": "鼠尾草绿"},
        "ST": {"en": "stone",          "zh": "石色 / 浅卡其"},
        "BL": {"en": "blue",           "zh": "蓝色"},

        # 精细色名（完全按 Product Color 对应）
        "PI": {"en": "Arabesque",              "zh": "偏玫瑰粉"},
        "BR": {"en": "Bark",                   "zh": "树皮棕"},
        "SN": {"en": "Beech/Classic",          "zh": "山毛榉浅棕"},
        "RE": {"en": "Bordeaux",               "zh": "波尔多红"},
        "ST": {"en": "Clay",                   "zh": "陶土色"},
        "WH": {"en": "Cloud",                  "zh": "白云色"},
        "GN": {"en": "Forest",                 "zh": "森林绿"},
        "TN": {"en": "Forest Mist",            "zh": "森林雾绿"},
        "BE": {"en": "Light Trench",           "zh": "浅风衣米色 / 浅卡其色"},
        "TN": {"en": "Midnight",               "zh": "午夜蓝 / 深蓝黑"},
        "BE": {"en": "Mist",                   "zh": "雾灰色 / 雾霾米色"},
        "CR": {"en": "Pearl",                  "zh": "珍珠白"},
        "BR": {"en": "Black Oak",              "zh": "黑橡木棕"},
        "OL": {"en": "Fern",                   "zh": "蕨绿色"},
        "BR": {"en": "Brown",                  "zh": "棕色"},                     # 与上面 brown 大致同义，保留
        "GN": {"en": "Dundee Tartan",          "zh": "Dundee 格纹绿色"},
        "BK": {"en": "Black Carbon",           "zh": "碳黑色"},
        "BR": {"en": "Umber",                  "zh": "棕褐色 / 赭棕"},
        "ST": {"en": "Light Fawn",             "zh": "浅鹿皮色 / 浅驼色"},
        "CR": {"en": "Pearl/Navy",             "zh": "珍珠白/海军蓝"},
        "BE": {"en": "Trench",                 "zh": "风衣米色"},
        "NY": {"en": "Navy/Classic",           "zh": "深蓝/经典格纹"},
        "OL": {"en": "Deep Olive/Ancient Tartan",      "zh": "深橄榄绿/Ancient 格纹"},
        "GN": {"en": "Olive",                  "zh": "橄榄绿调"},
        "BL": {"en": "Sky Micro Check",        "zh": "天蓝细格纹"},
        "OL": {"en": "Fern/Classic Tartan",    "zh": "蕨绿/经典格纹"},
        "BR": {"en": "Bark/Muted",             "zh": "树皮棕/柔和色调"},
        "OL": {"en": "Tan/Dress Tartan",       "zh": "茶色/礼服格纹"},
        "NY": {"en": "Royal Navy/Dress Tartan","zh": "皇家海军蓝/礼服格纹"},
        "TA": {"en": "Tan/Dress Tartan",       "zh": "茶色/礼服格纹"},
        "OL": {"en": "Fern/Ancient Tartan",    "zh": "蕨绿/Ancient 格纹"},
        "OL": {"en": "Archive Olive/Ancient Tartan", "zh": "Archive 橄榄/Ancient 格纹"},
        "RU": {"en": "Rustic/Ancient Tartan",  "zh": "乡村棕/Ancient 格纹"},
        "OL": {"en": "Fern/Beech/Ancient Tartan", "zh": "蕨绿/山毛榉/Ancient 格纹"},
        "OL": {"en": "Fern/Sage/Ancient Tartan",  "zh": "蕨绿/鼠尾草/Ancient 格纹"},

        # ===== 比较确定的基础色（你原来的第二段） =====
        "RE": {"en": "red",            "zh": "红色"},
        "PI": {"en": "pink",           "zh": "粉色"},
        "CR": {"en": "cream",          "zh": "奶油色 / 米白"},
        "CH": {"en": "charcoal",       "zh": "炭灰"},
        "TN": {"en": "tan",            "zh": "茶色 / 浅棕"},
        "KH": {"en": "khaki",          "zh": "卡其色"},
        "YE": {"en": "yellow",         "zh": "黄色"},
        "OR": {"en": "orange",         "zh": "橙色"},
        "PU": {"en": "purple",         "zh": "紫色 / 李子紫"},
        "IN": {"en": "indigo",         "zh": "靛蓝"},
        "TA": {"en": "taupe",          "zh": "灰褐色"},
        "CM": {"en": "camel",          "zh": "驼色"},
        "TE": {"en": "teal",           "zh": "水鸭蓝 / 墨绿蓝"},
        "CO": {"en": "cobalt",         "zh": "钴蓝色"},
        "AQ": {"en": "aqua",           "zh": "水绿色 / 青绿色"},

        # ===== Barbour 自己的特别几组 =====
        "BU": {"en": "burgundy",       "zh": "酒红"},
        "RU": {"en": "rustic",         "zh": "乡村棕 / 锈色"},
        "SN": {"en": "sand",           "zh": "沙色 / 砂岩色"},
        "BC": {"en": "black/charcoal", "zh": "黑炭灰"},
        "HG": {"en": "heather grey",   "zh": "杂灰 / 麻灰"},
        "ME": {"en": "merlot",         "zh": "酒红棕 / 梅洛红"},
    },


    "BARBOUR_COLOR_MAP" : {
        "classic navy": "海军蓝",
        "black": "黑色",
        "olive": "橄榄绿",
        "sage": "鼠尾草绿",
        "Military Brown": "军棕色",
        "Vintage Teal": "复古水鸭蓝",
        "sandstone": "砂岩色",
        "bark": "树皮棕",
        "rustic": "乡村棕",
        "stone": "石色",
        "charcoal": "炭灰",
        "navy": "深蓝",
        "blue": "蓝色",
        "light moss": "浅苔绿",
        "brown": "棕色",
        "dark brown": "深棕",
        "rust": "铁锈红",
        "red": "红色",
        "burgundy": "酒红",
        "yellow": "黄色",
        "mustard": "芥末黄",
        "khaki": "卡其色",
        "forest": "森林绿",
        "dusky green": "暗绿色",
        "uniform green": "军绿色",
        "emerald": "祖母绿",
        "antique pine": "古松木色",
        "pale pink": "浅粉",
        "pink": "粉色",
        "rose": "玫瑰粉",
        "cream": "奶油色",
        "off white": "米白",
        "white": "白色",
        "grey": "灰色",
        "mineral grey": "矿物灰",
        "washed cobalt": "钴蓝色",
        "timberwolf": "灰棕色",
        "burnt heather": "焦石楠色",
        "mist": "雾灰色",
        "concrete": "混凝土灰",
        "dark denim": "深牛仔蓝",
        "empire green": "帝国绿",
        "royal blue": "宝蓝",
        "classic tartan": "经典格纹",
        "tartan": "格纹",
        "beige": "米色",
        "tan": "茶色",
        "walnut": "胡桃棕",
        "plum": "李子紫",
        "orange": "橙色",
        "bronze": "青铜色",
        "silver": "银色",
        "pewter": "锡灰",
        "cola": "可乐棕",
        "taupe": "灰褐色",
    }

}



# === Terraces（Barbour）路径配置 ===
TERRACES_BASE = BASE_DIR / "terraces"
TERRACES = {
    "BRAND": "terraces",
    "BASE": TERRACES_BASE,
    "TXT_DIR": TERRACES_BASE / "publication" / "TXT",
    "OUTPUT_DIR": TERRACES_BASE / "repulibcation",
    "STORE_DIR": TERRACES_BASE / "document" / "store",
    "IMAGE_DIR": TERRACES_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": TERRACES_BASE / "document" / "images_download",
    "IMAGE_PROCESS": TERRACES_BASE / "document" / "images_process",
    "IMAGE_CUTTER": TERRACES_BASE / "document" / "images_cutter",
    "TABLE_NAME": "terraces_inventory",  # ✅ 数据库表名
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": TERRACES_BASE / "publication" / "product_links.txt",  # ✅ 商品链接文件
    "FIELDS": {
        "product_code": "product_code",  # 商品编码
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # 可改 stock_count
        "gender": "gender"
    }
}

# === Camper 经销商路径配置 ===
CAMPER_BASE = BASE_DIR / "camper"
CAMPER = {
    "BRAND": "camper",
    "BASE": CAMPER_BASE,
    "IMAGE_FIRST_PRIORITY": ["F", "C", "L", "T"],
    "IMAGE_DES_PRIORITY": ["C", "F", "L", "T"],
    "TXT_DIR": CAMPER_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": CAMPER_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": CAMPER_BASE / "document" / "DEF_images",
    "IMAGE_DIR": CAMPER_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": CAMPER_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": CAMPER_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": CAMPER_BASE / "publication" / "image_cutter",
    "MERGED_DIR": CAMPER_BASE / "document" / "image_merged",
    "HTML_DIR": CAMPER_BASE / "publication" / "html",
    "HTML_DIR_DES": CAMPER_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": CAMPER_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": CAMPER_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": CAMPER_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": CAMPER_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": CAMPER_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": CAMPER_BASE / "document" / "html_cutter"/ "first_page",
    "STORE_DIR": CAMPER_BASE / "document" / "store",
    "OUTPUT_DIR": CAMPER_BASE / "repulibcation",
    "TABLE_NAME": "camper_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CAMPER_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 实数库存
        "gender": "gender"
    }
}


REISS_BASE = BASE_DIR / "reiss"
REISS = {
    "BRAND": "reiss",
    "BASE": REISS_BASE,
    "IMAGE_FIRST_PRIORITY": ["s", "s3", "s4"],
    "IMAGE_DES_PRIORITY": ["s2", "s3", "s4", "s5"],
    "TXT_DIR": REISS_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": REISS_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": REISS_BASE / "document" / "DEF_images",
    "IMAGE_DIR": REISS_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": REISS_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": REISS_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": REISS_BASE / "publication" / "image_cutter",
    "MERGED_DIR": REISS_BASE / "document" / "image_merged",
    "HTML_DIR": REISS_BASE / "publication" / "html",
    "HTML_DIR_DES": REISS_BASE / "publication" / "html" / "description",
    "HTML_DIR_FIRST_PAGE": REISS_BASE / "publication" / "html" / "first_page",
    "HTML_IMAGE": REISS_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": REISS_BASE / "publication" / "html_image" / "description",
    "HTML_IMAGE_FIRST_PAGE": REISS_BASE / "publication" / "html_image" / "first_page",
    "HTML_CUTTER_DES": REISS_BASE / "document" / "html_cutter" / "description",
    "HTML_CUTTER_FIRST_PAGE": REISS_BASE / "document" / "html_cutter" / "first_page",
    "STORE_DIR": REISS_BASE / "document" / "store",
    "OUTPUT_DIR": REISS_BASE / "repulibcation",
    "TABLE_NAME": "reiss_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": REISS_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",
        "gender": "gender"
    }
}


# === Clarks 品牌路径配置 ===
CLARKS_BASE = BASE_DIR / "clarks"
CLARKS = {
    "BRAND": "clarks",
    "BASE": CLARKS_BASE,
    "TXT_DIR": CLARKS_BASE / "publication" / "TXT",
    "OUTPUT_DIR": CLARKS_BASE / "repulibcation",
    "STORE_DIR": CLARKS_BASE / "document" / "store",
    "IMAGE_DIR": CLARKS_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": CLARKS_BASE / "document" / "images_download",
    "IMAGE_PROCESS": CLARKS_BASE / "document" / "images_process",
    "IMAGE_CUTTER": CLARKS_BASE / "document" / "images_CUTTER",
    "MERGED_DIR": CLARKS_BASE / "document" / "image_merged",
    "HTML_IMAGE": CLARKS_BASE / "document" / "html_image",
    "HTML_CUTTER": CLARKS_BASE / "document" / "html_cutter",
    "HTML_DIR": CLARKS_BASE / "document" / "html",
    "TABLE_NAME": "clarks_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CLARKS_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # 仍为文本
        "gender": "gender"
    }
}


# === Clarks 鲸芽供货商模式路径配置 ===
CLARKS_JINGYA_BASE = BASE_DIR / "clarks_jingya"
CLARKS_JINGYA = {
    "BRAND": "clarks_jingya",
    "BASE": CLARKS_JINGYA_BASE,
    "IMAGE_PRIORITY": ["1", "6", "4", "2"],
    "IMAGE_FIRST_PRIORITY": ["1", "6", "4", "2"],
    "IMAGE_DES_PRIORITY": ["6", "1", "4", "2"],
    "TXT_DIR": CLARKS_JINGYA_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": CLARKS_JINGYA_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": CLARKS_JINGYA_BASE / "document" / "DEF_images",
    "IMAGE_DIR": CLARKS_JINGYA_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": CLARKS_JINGYA_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": CLARKS_JINGYA_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": CLARKS_JINGYA_BASE / "publication" / "image_cutter",
    "MERGED_DIR": CLARKS_JINGYA_BASE / "document" / "image_merged",
    "HTML_DIR": CLARKS_JINGYA_BASE / "publication" / "html",
    "HTML_DIR_DES": CLARKS_JINGYA_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": CLARKS_JINGYA_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": CLARKS_JINGYA_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": CLARKS_JINGYA_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": CLARKS_JINGYA_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": CLARKS_JINGYA_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": CLARKS_JINGYA_BASE / "document" / "html_cutter"/ "first_page",
    "STORE_DIR": CLARKS_JINGYA_BASE / "document" / "store",
    "OUTPUT_DIR": CLARKS_JINGYA_BASE / "repulibcation",
    "TABLE_NAME": "clarks_jingya_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CLARKS_JINGYA_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 改为数值库存
        "gender": "gender"
    }
}


# === BIRKENSTOCK 品牌路径配置 ===
BIRKENSTOCK_BASE = BASE_DIR / "birkenstock"
BIRKENSTOCK = {
    "BRAND": "birkenstock",
    "BASE": BIRKENSTOCK_BASE,
    "TXT_DIR": BIRKENSTOCK_BASE / "publication" / "TXT",
    "OUTPUT_DIR": BIRKENSTOCK_BASE / "repulibcation",
    "STORE_DIR": BIRKENSTOCK_BASE / "document" / "store",
    "IMAGE_DIR": BIRKENSTOCK_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": BIRKENSTOCK_BASE / "document" / "images_download",
    "IMAGE_PROCESS": BIRKENSTOCK_BASE / "document" / "images_process",
    "IMAGE_CUTTER": BIRKENSTOCK_BASE / "document" / "images_cutter",
    "TABLE_NAME": "birkenstock_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": BIRKENSTOCK_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",
        "gender": "gender"
    }
}

# === GEOX 品牌路径配置 ===
GEOX_BASE = BASE_DIR / "geox"
GEOX = {
    "BRAND": "geox",
    "BASE": GEOX_BASE,
    "IMAGE_PRIORITY": ["1", "6", "4", "2"],
    "IMAGE_FIRST_PRIORITY": ["07", "00", "01", "2"],
    "IMAGE_DES_PRIORITY": ["01", "00", "07", "2"],
    "TXT_DIR": GEOX_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": GEOX_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": GEOX_BASE / "document" / "DEF_images",
    "IMAGE_DIR": GEOX_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": GEOX_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": GEOX_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": GEOX_BASE / "publication" / "image_cutter",
    "MERGED_DIR": GEOX_BASE / "document" / "image_merged",
    "HTML_DIR": GEOX_BASE / "publication" / "html",
    "HTML_DIR_DES": GEOX_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": GEOX_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": GEOX_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": GEOX_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": GEOX_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": GEOX_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": GEOX_BASE / "document" / "html_cutter"/ "first_page",
    "STORE_DIR": GEOX_BASE / "document" / "store",
    "OUTPUT_DIR": GEOX_BASE / "repulibcation",
    "TABLE_NAME": "geox_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": GEOX_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 改为数值库存
        "gender": "gender"
    }
}

MARKSANDSPENCER_BASE = BASE_DIR / "marksandspencer"
MARKSANDSPENCER = {
    "BRAND": "marksandspencer",
    "BASE": MARKSANDSPENCER_BASE,
    "IMAGE_FIRST_PRIORITY": ["F", "C", "L", "T"],
    "IMAGE_DES_PRIORITY": ["C", "F", "L", "T"],
    "TXT_DIR": MARKSANDSPENCER_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": MARKSANDSPENCER_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": MARKSANDSPENCER_BASE / "document" / "DEF_images",
    "IMAGE_DIR": MARKSANDSPENCER_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": MARKSANDSPENCER_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": MARKSANDSPENCER_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": MARKSANDSPENCER_BASE / "publication" / "image_cutter",
    "MERGED_DIR": MARKSANDSPENCER_BASE / "document" / "image_merged",
    "HTML_DIR": MARKSANDSPENCER_BASE / "publication" / "html",
    "HTML_DIR_DES": MARKSANDSPENCER_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": MARKSANDSPENCER_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": MARKSANDSPENCER_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": MARKSANDSPENCER_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": MARKSANDSPENCER_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": MARKSANDSPENCER_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": MARKSANDSPENCER_BASE / "document" / "html_cutter"/ "first_page",
    "STORE_DIR": MARKSANDSPENCER_BASE / "document" / "store",
    "OUTPUT_DIR": MARKSANDSPENCER_BASE / "repulibcation",
    "TABLE_NAME": "marksandspencer_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE_JACKET": MARKSANDSPENCER_BASE / "marksandspencer" / "publication" / "links_jacket.txt",
    "LINKS_FILE_LINGERIE": MARKSANDSPENCER_BASE / "marksandspencer" / "publication" / "links_lingerie.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 实数库存
        "gender": "gender"
    }
}

# === ECCO 品牌路径配置 ===
ECCO_BASE = BASE_DIR / "ecco"
ECCO = {
    "BRAND": "ecco",
    "BASE": ECCO_BASE,
    "IMAGE_FIRST_PRIORITY": ["m", "o", "L", "T"],
    "IMAGE_DES_PRIORITY": ["top_left_pair", "o", "m", "T"],
    "TXT_DIR": ECCO_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": ECCO_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": ECCO_BASE / "document" / "DEF_images",
    "IMAGE_DIR": ECCO_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": ECCO_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": ECCO_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": ECCO_BASE / "publication" / "image_cutter",
    "MERGED_DIR": ECCO_BASE / "document" / "image_merged",
    "HTML_DIR": ECCO_BASE / "publication" / "html",
    "HTML_DIR_DES": ECCO_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": ECCO_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": ECCO_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": ECCO_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": ECCO_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": ECCO_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": ECCO_BASE / "document" / "html_cutter"/ "first_page",
    "STORE_DIR": ECCO_BASE / "document" / "store",
    "OUTPUT_DIR": ECCO_BASE / "repulibcation",
    "TABLE_NAME": "ECCO_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": ECCO_BASE / "publication" / "product_links.txt",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 实数库存
        "gender": "gender"
    }
}

# === 品牌映射 ===
BRAND_CONFIG = {
    "clarks": CLARKS,
    "clarks_jingya": CLARKS_JINGYA,
    "camper": CAMPER,
    "geox": GEOX,
    "ecco": ECCO,
    "birkenstock": BIRKENSTOCK,
    "barbour": BARBOUR,  # ✅ 加这一行
    "reiss": REISS,   # ✅ 加这一行
    "marksandspencer": MARKSANDSPENCER # ✅ 新增
}


# ==== 品牌中英文名映射 ====
BRAND_NAME_MAP = {
    "camper": ("Camper", "看步"),
    "clarks": ("Clarks", "其乐"),
    "clarks_jingya": ("Clarks", "其乐"),
    "geox": ("GEOX", "健乐士"),
    "ecco": ("ECCO", "爱步"),
    "barbour": ("Barbour", "巴伯尔"),
    "birkenstock": ("BIRKENSTOCK", "勃肯"),
    "reiss": ("REISS", ""),  # ✅ 新增（中文名若需本地化可改为“瑞斯/锐思”等）
    "ms": ("Marks & Spencer", "马莎"),  # ✅ 新增
}

BRAND_DISCOUNT = {
    "camper": 0.71,
    "geox": 0.98,
    "clarks_jingya": 1.0,
    "ecco": 0.9,
    # 其它品牌默认 1.0
}