from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

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
