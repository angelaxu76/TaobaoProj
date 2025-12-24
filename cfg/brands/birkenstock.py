from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

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