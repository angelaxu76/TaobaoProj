from pathlib import Path

# === 数据库连接配置 ===
PGSQL_CONFIG = {
    "host": "192.168.5.9",
    "port": 5432,
    "user": "postgres",
    "password": "516518",  # 请根据实际情况替换
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

# === 通用工具函数（可选） ===
def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)



# === BIRKENSTOCK 品牌路径配置 ===

BIRKENSTOCK = {
    "BRAND": "birkenstock",
    "TXT_DIR": Path("D:/TB/Products/birkenstock/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/birkenstock/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/birkenstock/document/store"),
    "BASE": Path("D:/TB/Products/birkenstock"),
    "TABLE_NAME": "birkenstock_inventory",
    "IMAGE_DIR": Path("D:/TB/Products/birkenstock/document/images"),
    "IMAGE_DOWNLOAD": Path("D:/TB/Products/birkenstock/document/images_download"),
    "IMAGE_PROCESS": Path("D:/TB/Products/birkenstock/document/images_process"),
    "IMAGE_CUTTER": Path("D:/TB/Products/birkenstock/document/images_cutter"),
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": Path("D:/TB/Products/birkenstock/publication/product_links.txt"),
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
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

# === Clarks 品牌路径配置 ===
# === Clarks 品牌路径配置 ===
CLARKS = {
    "BRAND": "clarks",
    "TXT_DIR": Path("D:/TB/Products/clarks/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/clarks/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/clarks/document/store"),
    "BASE": Path("D:/TB/Products/clarks"),
    "TABLE_NAME": "clarks_inventory",
    "IMAGE_DOWNLOAD": Path("D:/TB/Products/clarks/document/images_download"),
    "IMAGE_TEMP": Path("D:/TB/Products/clarks/document/images_TEMP"),
    "IMAGE_CUTTER": Path("D:/TB/Products/clarks/document/images_CUTTER"),
    "IMAGE_DIR": Path("D:/TB/Products/clarks/document/images"),
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": Path("D:/TB/Products/clarks/publication/product_links.txt"),
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # ✅ 文本类型，有货/无货
        "gender": "gender"  # ✅ 加上这一行
    }
}

# === Camper 品牌路径配置 ===
CAMPER = {
    "BASE": BASE_DIR / "camper",
    "TXT_DIR": BASE_DIR / "camper" / "publication" / "TXT",
    "ORG_IMAGE_DIR": BASE_DIR / "camper" / "document" / "orgin_images",
    "DEF_IMAGE_DIR": BASE_DIR / "camper" / "document" / "DEF_images",
    "IMAGE_DIR": BASE_DIR / "camper" / "document" / "images",
    "STORE_DIR": BASE_DIR / "camper" / "document" / "store",
    "OUTPUT_DIR": BASE_DIR / "camper" / "repulibcation",
    "TABLE_NAME": "camper_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": BASE_DIR / "camper" / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 数值类型，>0 表示有货
        "gender": "gender"  # ✅ 加上这一行
    }
}

# === Geox 品牌路径配置 ===
GEOX = {
    "TXT_DIR": Path("D:/TB/Products/geox/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/geox/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/geox/document/store"),
    "BASE": Path("D:/TB/Products/geox"),
    "TABLE_NAME": "geox_inventory",
    "IMAGE_DIR": Path("D:/TB/Products/geox/document/images"),
    "IMAGE_DOWNLOAD": Path("D:/TB/Products/geox/document/images_DOWNLOAD"),
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": Path("D:/TB/Products/geox/publication/product_links.txt"),
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # ✅ 请确保 GEOX 表使用文本库存状态
        "gender": "gender"  # ✅ 加上这一行
    }
}

# === ECCO 品牌路径配置 ===
ECCO = {
    "TXT_DIR": Path("D:/TB/Products/ecco/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/ecco/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/ecco/document/store"),
    "BASE": Path("D:/TB/Products/ecco"),
    "TABLE_NAME": "ecco_inventory",
    "IMAGE_DIR": Path("D:/TB/Products/ecco/document/images"),
    "IMAGE_DIR_download": Path("D:/TB/Products/ecco/document/images_download"),
    "IMAGE_DIR_defence": Path("D:/TB/Products/ecco/document/image_defence"),
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": Path("D:/TB/Products/ecco/publication/product_links.txt"),
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_status",  # ✅ 如果 ECCO 使用数值库存，请改为 stock_count
        "gender": "gender"  # ✅ 加上这一行
    }
}




BRAND_CONFIG = {
    "clarks": CLARKS,
    "camper": CAMPER,
    "geox": GEOX,
    "ecco": ECCO,
    "birkenstock": BIRKENSTOCK  # ✅ 加入这一行
}