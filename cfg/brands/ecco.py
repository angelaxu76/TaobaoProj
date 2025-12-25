from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

ECCO_BASE = BASE_DIR / "ecco"
ECCO = {
    "BRAND": "ecco",
    "BASE": ECCO_BASE,
    "IMAGE_FIRST_PRIORITY": ["m", "o", "L", "T"],
    "IMAGE_DES_PRIORITY": ["top_left_pair", "o", "m", "T"],
    "TXT_DIR": ECCO_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": ECCO_BASE / "publication" / "orgin_images",
    "DEF_IMAGE_DIR": ECCO_BASE / "publication" / "DEF_images",
    "IMAGE_DIR": ECCO_BASE / "publication" / "images",
    "IMAGE_DOWNLOAD": ECCO_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": ECCO_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": ECCO_BASE / "publication" / "image_cutter",
    "MERGED_DIR": ECCO_BASE / "publication" / "image_merged",
    "HTML_DIR": ECCO_BASE / "publication" / "html",
    "HTML_DIR_DES": ECCO_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": ECCO_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": ECCO_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": ECCO_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": ECCO_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": ECCO_BASE / "publication" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": ECCO_BASE / "publication" / "html_cutter"/ "first_page",
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
