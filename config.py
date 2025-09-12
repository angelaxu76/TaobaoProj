from pathlib import Path

# === 数据库连接配置 ===
PGSQL_CONFIG = {
    "host": "192.168.5.9",
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


# === 项目根路径 ===
BASE_DIR = Path("D:/TB/Products")
DISCOUNT_EXCEL_DIR = Path("D:/TB/DiscountCandidates")
TAOBAO_STORES = ["五小剑", "英国伦敦代购2015"]

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
        "童款": ["24", "25", "26", "27", "28", "29", "30", "31","32", "33", "34", "35","36", "37","38", "39"]  # Clarks 暂不处理童款时可留空或补上
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
    "IMAGE_DIR": BARBOUR_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": BARBOUR_BASE / "document" / "images_download",
    "IMAGE_PROCESS": BARBOUR_BASE / "document" / "images_process",
    "IMAGE_CUTTER": BARBOUR_BASE / "document" / "images_cutter",
    "HTML_DIR": BARBOUR_BASE / "publication" / "html",
    "HTML_DIR_DES": BARBOUR_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": BARBOUR_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": BARBOUR_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": BARBOUR_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": BARBOUR_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": BARBOUR_BASE / "document" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": BARBOUR_BASE / "document" / "html_cutter"/ "first_page",
    "HTML_DEST": BARBOUR_BASE / "document" / "dest",
    "TABLE_NAME": "barbour_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": BARBOUR_BASE / "publication" / "barbour" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
    # === 新增 houseoffraser 配置 ===
# === 新增 very 配置 ===
    "LINKS_FILES": {
        "outdoorandcountry": BARBOUR_BASE / "publication" / "outdoorandcountry" / "product_links.txt",
        "allweathers": BARBOUR_BASE / "publication" / "allweathers" / "product_links.txt",
        "barbour": BARBOUR_BASE / "publication" / "barbour" / "product_links.txt",
        "houseoffraser": BARBOUR_BASE / "publication" / "houseoffraser" / "product_links.txt",  # ✅ 新增
        "philipmorris": BARBOUR_BASE / "publication" / "philipmorris" / "product_links.txt",  # ✅ 新增
        "very": BARBOUR_BASE / "publication" / "very" / "product_links.txt",  # ✅ 新增
        "terraces": BARBOUR_BASE / "publication" / "terraces" / "product_links.txt",
    },

    "TXT_DIRS": {
        "all": BARBOUR_BASE / "publication" / "TXT",  # ✅ 新增
        "outdoorandcountry": BARBOUR_BASE / "publication" / "outdoorandcountry" / "TXT",
        "allweathers": BARBOUR_BASE / "publication" / "allweathers" / "TXT",  # 👈 修复
        "barbour": BARBOUR_BASE / "publication" / "barbour" / "TXT",          # 👈 修复
        "houseoffraser": BARBOUR_BASE / "publication" / "houseoffraser" / "TXT",  # ✅ 新增
        "philipmorris": BARBOUR_BASE / "publication" / "philipmorris" / "TXT",    # ✅ 新增
        "very": BARBOUR_BASE / "publication" / "very" / "TXT",  # ✅ 新增
        "terraces": BARBOUR_BASE / "publication" / "terraces" / "TXT",
    },

    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",
        "gender": "gender"
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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
    "TXT_DIR": GEOX_BASE / "publication" / "TXT",
    "OUTPUT_DIR": GEOX_BASE / "repulibcation",
    "STORE_DIR": GEOX_BASE / "document" / "store",
    "IMAGE_DIR": GEOX_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": GEOX_BASE / "document" / "images_DOWNLOAD",
    "TABLE_NAME": "geox_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": GEOX_BASE / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Projects/chromedriver-win64/chromedriver.exe",
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

# === ECCO 品牌路径配置 ===
ECCO_BASE = BASE_DIR / "ecco"
ECCO = {
    "BRAND": "ecco",
    "BASE": ECCO_BASE,
    "IMAGE_FIRST_PRIORITY": ["F", "C", "L", "T"],
    "IMAGE_DES_PRIORITY": ["C", "F", "L", "T"],
    "TXT_DIR": ECCO_BASE / "publication" / "TXT",
    "OUTPUT_DIR": ECCO_BASE / "repulibcation",
    "STORE_DIR": ECCO_BASE / "document" / "store",
    "IMAGE_DIR": ECCO_BASE / "document" / "images",
    "IMAGE_DIR_download": ECCO_BASE / "document" / "images_download",
    "IMAGE_DIR_defence": ECCO_BASE / "document" / "image_defence",
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
    "TABLE_NAME": "ecco_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": ECCO_BASE / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # 若改为数值库存请统一成 stock_count
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
    "reiss": REISS  # ✅ 加这一行
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
}
