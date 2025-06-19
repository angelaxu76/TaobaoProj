from pathlib import Path

# === 数据库连接配置 ===
PGSQL_CONFIG = {
    "host": "192.168.5.9",
    "port": 5432,
    "user": "postgres",
    "password": "516518",  # 请根据实际情况替换
    "dbname": "taobao_inventory_db"
}

# === 项目根路径 ===
BASE_DIR = Path("D:/TB/Products")

# === Clarks 品牌路径配置 ===
CLARKS = {
    "TXT_DIR": Path("D:/TB/Products/clarks/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/clarks/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/clarks/document/store"),
    "BASE": Path("D:/TB/Products/clarks"),
    "TABLE_NAME": "clarks_inventory",
    "IMAGE_DIR": Path("D:/TB/Products/clarks/document/images"),  # ✅ 添加这个
    "PGSQL_CONFIG": PGSQL_CONFIG  # ✅ 加上这一行
}
# === Camper 品牌路径配置（可继续扩展） ===
CAMPER = {
    "BASE": BASE_DIR / "camper",
    "TXT_DIR": BASE_DIR / "camper" / "publication" / "TXT",
    "IMAGE_DIR": BASE_DIR / "camper" / "publication" / "images",
    "STORE_DIR": BASE_DIR / "camper" / "document" / "store",
    "OUTPUT_DIR": BASE_DIR / "camper" / "output"
}

# === Geox 品牌路径配置（可继续扩展） ===
GEOX = {
    "TXT_DIR": Path("D:/TB/Products/geox/publication/TXT"),
    "OUTPUT_DIR": Path("D:/TB/Products/geox/repulibcation"),
    "STORE_DIR": Path("D:/TB/Products/geox/document/store"),
    "BASE": Path("D:/TB/Products/geox"),
    "TABLE_NAME": "geox_inventory",
    "IMAGE_DIR": Path("D:/TB/Products/geox/document/images"),
    "PGSQL_CONFIG": PGSQL_CONFIG
}


# === ECCO 品牌路径配置（可继续扩展） ===
ECCO = {
    "BASE": BASE_DIR / "ecco",
    "TXT_DIR": BASE_DIR / "ecco" / "publication" / "TXT",
    "IMAGE_DIR": BASE_DIR / "ecco" / "document" / "images",
    "STORE_DIR": BASE_DIR / "ecco" / "document" / "store",
    "OUTPUT_DIR": BASE_DIR / "ecco" / "output",
    "TABLE_NAME": "ecco_inventory",
    "PGSQL_CONFIG": PGSQL_CONFIG
}


BRAND_CONFIG = {
    "clarks": CLARKS,
    "camper": CAMPER,
    "geox": GEOX,
    "ecco": ECCO
}

# === 通用工具函数（可选） ===
def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
