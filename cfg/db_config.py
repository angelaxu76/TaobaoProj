# config/db_config.py
# PGSQL_CONFIG = {
#     "host": "192.168.1.44",
#     "port": 5432,
#     "user": "postgres",
#     "password": "516518",
#     "dbname": "taobao_inventory_db",
# }

PGSQL_CONFIG = {
    "host": "192.168.1.44",
    "port": 5432,
    "user": "postgres",
    "password": "516518",
    "dbname": "eminzora_inventory_db",
}

# 每个品牌对应一个库存表名（通用脚本就靠这个映射）
BRAND_TABLE = {
    "camper": "camper_inventory",
    "clarks_jingya": "clarks_jingya_inventory",
    "ecco": "ecco_inventory",
    "geox": "geox_inventory",
    "barbour": "barbour_inventory",
}