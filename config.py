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

# === Camper 经销商路径配置 ===
CAMPER_BASE = BASE_DIR / "camper"
CAMPER = {
    "BRAND": "camper",
    "BASE": CAMPER_BASE,
    "TXT_DIR": CAMPER_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": CAMPER_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": CAMPER_BASE / "document" / "DEF_images",
    "IMAGE_DIR": CAMPER_BASE / "document" / "images",
    "STORE_DIR": CAMPER_BASE / "document" / "store",
    "OUTPUT_DIR": CAMPER_BASE / "repulibcation",
    "TABLE_NAME": "camper_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CAMPER_BASE / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
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

# === Camper Global（调货）路径配置 ===
CAMPER_GLOBAL_BASE = BASE_DIR / "camper_global"
CAMPER_GLOBAL = {
    "BRAND": "camper_global",
    "BASE": CAMPER_GLOBAL_BASE,
    "TXT_DIR": CAMPER_GLOBAL_BASE / "publication" / "TXT",
    "OUTPUT_DIR": CAMPER_GLOBAL_BASE / "repulibcation",
    "STORE_DIR": CAMPER_GLOBAL_BASE / "document" / "store",
    "IMAGE_DIR": CAMPER_GLOBAL_BASE / "document" / "image",
    "TABLE_NAME": "camper_inventory_global",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CAMPER_GLOBAL_BASE / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
    "FIELDS": {
        "product_code": "product_code",
        "url": "product_url",
        "discount_price": "discount_price_gbp",
        "original_price": "original_price_gbp",
        "size": "size",
        "stock": "stock_count",  # ✅ 改为数值型
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
    "IMAGE_TEMP": CLARKS_BASE / "document" / "images_TEMP",
    "IMAGE_CUTTER": CLARKS_BASE / "document" / "images_CUTTER",
    "TABLE_NAME": "clarks_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CLARKS_BASE / "publication" / "product_links.txt",
    "CHROMEDRIVER_PATH": "D:/Software/chromedriver-win64/chromedriver.exe",
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

# === ECCO 品牌路径配置 ===
ECCO_BASE = BASE_DIR / "ecco"
ECCO = {
    "BRAND": "ecco",
    "BASE": ECCO_BASE,
    "TXT_DIR": ECCO_BASE / "publication" / "TXT",
    "OUTPUT_DIR": ECCO_BASE / "repulibcation",
    "STORE_DIR": ECCO_BASE / "document" / "store",
    "IMAGE_DIR": ECCO_BASE / "document" / "images",
    "IMAGE_DIR_download": ECCO_BASE / "document" / "images_download",
    "IMAGE_DIR_defence": ECCO_BASE / "document" / "image_defence",
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
    "camper": CAMPER,
    "camper_global": CAMPER_GLOBAL,
    "geox": GEOX,
    "ecco": ECCO,
    "birkenstock": BIRKENSTOCK
}
