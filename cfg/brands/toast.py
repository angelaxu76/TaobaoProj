from ..paths import BASE_DIR
from ..db_config import PGSQL_CONFIG

TOAST_BASE = BASE_DIR / "toast"
TOAST = {
    "BRAND": "toast",
    "BASE": TOAST_BASE,
    "SITE_ROOT": "https://www.toa.st",
    # 站点有 Cloudflare，请求过密会封 IP；所有请求之间的最小间隔（秒）
    "REQUEST_MIN_INTERVAL": 1.5,
    "FEATURE_DELIMITER": "|",
    "TXT_DIR": TOAST_BASE / "publication" / "TXT",
    "ORG_IMAGE_DIR": TOAST_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": TOAST_BASE / "document" / "DEF_images",
    "IMAGE_DIR": TOAST_BASE / "document" / "images",
    "IMAGE_DOWNLOAD": TOAST_BASE / "publication" / "image_download",
    # 商品视频（下载图片时一并下载）：{编码}_{序号}.mp4
    "VIDEO_DOWNLOAD": TOAST_BASE / "publication" / "video_download",
    "IMAGE_PROCESS": TOAST_BASE / "publication" / "image_process",
    "IMAGE_CUTTER": TOAST_BASE / "publication" / "image_cutter",
    "MERGED_DIR": TOAST_BASE / "document" / "image_merged",
    "HTML_DIR": TOAST_BASE / "publication" / "html",
    "HTML_DIR_DES": TOAST_BASE / "publication" / "html" / "description",
    "HTML_DIR_FIRST_PAGE": TOAST_BASE / "publication" / "html" / "first_page",
    "HTML_IMAGE": TOAST_BASE / "publication" / "html_image",
    "HTML_IMAGE_DES": TOAST_BASE / "publication" / "html_image" / "description",
    "HTML_IMAGE_FIRST_PAGE": TOAST_BASE / "publication" / "html_image" / "first_page",
    # 尺码表：{编码}_size.json（原始数据）+ {编码}_size.html（中文页面），截图输出到 SIZE_CHART_IMAGE_DIR
    "SIZE_CHART_DIR": TOAST_BASE / "publication" / "size",
    "SIZE_CHART_IMAGE_DIR": TOAST_BASE / "publication" / "size_image",
    "STORE_DIR": TOAST_BASE / "document" / "store",
    "OUTPUT_DIR": TOAST_BASE / "repulibcation",
    "TABLE_NAME": "toast_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE": TOAST_BASE / "publication" / "product_links.txt",
    # Shopify collection handle -> 默认性别（商品 tag 里有 gender 时以 tag 为准）
    # 需要抓特价时把 womens-sale / mens-sale 打开（里面混有鞋，collect 时按 EXCLUDE_PRODUCT_TYPE_KEYWORDS 过滤）
    "COLLECTIONS": {
        "womens-clothing": "Women",
        "mens-clothing": "Men",
        "womens-accessories": "Women",
        "mens-accessories": "Men",
        # "womens-sale": "Women",
        # "mens-sale": "Men",
    },
    # None = 全部保留；设为 ["TOAST"] 则只保留自有品牌（配饰里有 Falke / Hestra 等第三方品牌）
    "VENDOR_FILTER": None,
    # product_type 含这些词的商品不收（只要衣服和配件，不要鞋）
    "EXCLUDE_PRODUCT_TYPE_KEYWORDS": ["Shoes", "Sandals", "Trainers", "Boots", "Slippers", "Clogs"],
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
