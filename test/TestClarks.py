from common_taobao.db_import import import_txt_to_db
from config import CLARKS, PGSQL_CONFIG
import psycopg2

conn = psycopg2.connect(**PGSQL_CONFIG)

import_txt_to_db(
    txt_dir=CLARKS["TXT_DIR"],
    brand="clarks",
    conn=conn
)
