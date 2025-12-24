from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

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