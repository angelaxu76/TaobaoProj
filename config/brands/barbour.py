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
        "flannels":          BARBOUR_BASE / "publication" / "flannels" / "product_links.txt",
        "cho":               BARBOUR_BASE / "publication" / "cho" / "product_links.txt",
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

        "cho": {
            "strategy": "all_ratio",
            "extra_ratio": 0.95,
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
        "flannels":          BARBOUR_BASE / "publication" / "flannels" / "TXT",
        "cho":               BARBOUR_BASE / "publication" / "cho" / "TXT", 
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
    },
}