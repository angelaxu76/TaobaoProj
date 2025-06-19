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
    "BASE": BASE_DIR / "clarks",
    "TXT_DIR": BASE_DIR / "clarks" / "publication" / "TXT",
    "IMAGE_DIR": BASE_DIR / "clarks" / "document" / "images",
    "STORE_DIR": BASE_DIR / "clarks" / "document" / "store",
    "FETCH_SCRIPT": BASE_DIR / "clarks" / "core" / "FetchImangeAndInfo.py",
    "OUTPUT_DIR": BASE_DIR / "clarks" / "repulibcation"

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
    "BASE": BASE_DIR / "geox",
    "TXT_DIR": BASE_DIR / "geox" / "publication" / "TXT",
    "IMAGE_DIR": BASE_DIR / "geox" / "publication" / "images",
    "STORE_DIR": BASE_DIR / "geox" / "document" / "store",
    "OUTPUT_DIR": BASE_DIR / "geox" / "output"
}

# === ECCO 品牌路径配置（可继续扩展） ===
ECCO = {
    "BASE": BASE_DIR / "ecco",
    "TXT_DIR": BASE_DIR / "ecco" / "publication" / "TXT",
    "IMAGE_DIR": BASE_DIR / "ecco" / "document" / "images",
    "STORE_DIR": BASE_DIR / "ecco" / "document" / "store",
    "OUTPUT_DIR": BASE_DIR / "ecco" / "output"
}

# === 通用工具函数（可选） ===
def ensure_all_dirs(*dirs):
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
