from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

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
