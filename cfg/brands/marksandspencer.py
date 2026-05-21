from ..paths import BASE_DIR, GEI_SHARED_BASE
from ..db_config import PGSQL_CONFIG

MARKSANDSPENCER_BASE = BASE_DIR / "marksandspencer"
_PUB = MARKSANDSPENCER_BASE / "publication"

MARKSANDSPENCER = {
    "BRAND": "marksandspencer",
    "BASE": MARKSANDSPENCER_BASE,
    "GEI_DIR": GEI_SHARED_BASE / "marksandspencer",
    "FEATURE_DELIMITER": "|",
    "IMAGE_FIRST_PRIORITY": ["front_1_faceswap", "front_2_faceswap", "1", "2"],
    "IMAGE_DES_PRIORITY": ["front_2_faceswap", "1", "2", "3"],
    # ── 文本 ──────────────────────────────────────────────────────
    "TXT_DIR": _PUB / "TXT",
    # ── 图片处理流程（均在 publication/ 下，整批清理只需清此目录）──
    "IMAGE_DOWNLOAD":  _PUB / "image_download",   # Step 0a: 下载原图
    "IMAGE_PROCESS":   _PUB / "image_process",    # Step 0c: 抠图+白底
    "IMAGE_FINAL":     _PUB / "image_final",      # 换脸图+平铺汇集 → HTML 输入
    "IMAGE_CUTTER":    _PUB / "image_cutter",
    "MERGED_DIR":      _PUB / "image_merged",     # Step 1: 横向合并图
    # ── HTML 生成 ─────────────────────────────────────────────────
    "HTML_DIR":               _PUB / "html",
    "HTML_DIR_DES":           _PUB / "html" / "description",
    "HTML_DIR_FIRST_PAGE":    _PUB / "html" / "first_page",
    "HTML_IMAGE":             _PUB / "html_image",
    "HTML_IMAGE_DES":         _PUB / "html_image" / "description",
    "HTML_IMAGE_FIRST_PAGE":  _PUB / "html_image" / "first_page",
    "HTML_CUTTER_DES":        _PUB / "html_cutter" / "description",
    "HTML_CUTTER_FIRST_PAGE": _PUB / "html_cutter" / "first_page",
    # ── 其他 ──────────────────────────────────────────────────────
    "OUTPUT_DIR": _PUB,
    "STORE_DIR":  MARKSANDSPENCER_BASE / "document" / "store",
    # ── legacy（不在新流程中使用）────────────────────────────────
    "ORG_IMAGE_DIR": MARKSANDSPENCER_BASE / "document" / "orgin_images",
    "DEF_IMAGE_DIR": MARKSANDSPENCER_BASE / "document" / "DEF_images",
    "IMAGE_DIR":     MARKSANDSPENCER_BASE / "document" / "images",
    # ── 数据库 ────────────────────────────────────────────────────
    "TABLE_NAME": "marksandspencer_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG,
    "LINKS_FILE_JACKET":   _PUB / "links_jacket.txt",
    "LINKS_FILE_LINGERIE": _PUB / "links_lingerie.txt",
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
