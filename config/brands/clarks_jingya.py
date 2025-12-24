from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG


# === Clarks 鲸芽供货商模式路径配置 ===
CLARKS_JINGYA_BASE = BASE_DIR / "clarks_jingya"
CLARKS_JINGYA = {
    "BRAND": "clarks_jingya",
    "BASE": CLARKS_JINGYA_BASE,
    "IMAGE_PRIORITY": ["1", "6", "4", "2"],
    "IMAGE_FIRST_PRIORITY": ["1", "6", "4", "2"],
    "IMAGE_DES_PRIORITY": ["6", "1", "4", "2"],
    "TXT_DIR": CLARKS_JINGYA_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": CLARKS_JINGYA_BASE / "publication" / "orgin_images",
    "DEF_IMAGE_DIR": CLARKS_JINGYA_BASE / "publication" / "DEF_images",
    "IMAGE_DIR": CLARKS_JINGYA_BASE / "publication" / "images",
    "IMAGE_DOWNLOAD": CLARKS_JINGYA_BASE / "publication" / "image_download",
    "IMAGE_PROCESS": CLARKS_JINGYA_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": CLARKS_JINGYA_BASE / "publication" / "image_cutter",
    "MERGED_DIR": CLARKS_JINGYA_BASE / "publication" / "image_merged",
    "HTML_DIR": CLARKS_JINGYA_BASE / "publication" / "html",
    "HTML_DIR_DES": CLARKS_JINGYA_BASE / "publication" / "html"/ "description",
    "HTML_DIR_FIRST_PAGE": CLARKS_JINGYA_BASE / "publication" / "html"/ "first_page",
    "HTML_IMAGE": CLARKS_JINGYA_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": CLARKS_JINGYA_BASE / "publication" / "html_image"/ "description",
    "HTML_IMAGE_FIRST_PAGE": CLARKS_JINGYA_BASE / "publication" / "html_image"/"first_page",
    "HTML_CUTTER_DES": CLARKS_JINGYA_BASE / "publication" / "html_cutter"/ "description",
    "HTML_CUTTER_FIRST_PAGE": CLARKS_JINGYA_BASE / "publication" / "html_cutter"/ "first_page",
    "STORE_DIR": CLARKS_JINGYA_BASE / "document" / "store",
    "OUTPUT_DIR": CLARKS_JINGYA_BASE / "repulibcation",
    "TABLE_NAME": "clarks_jingya_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": CLARKS_JINGYA_BASE / "publication" / "product_links.txt",
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