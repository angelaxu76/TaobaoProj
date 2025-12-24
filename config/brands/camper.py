from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG


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