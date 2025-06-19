
import psycopg2
from config import CLARKS, PGSQL_CONFIG
from common_taobao.db_import import import_txt_to_db, import_skuid_from_store_excels
from pathlib import Path

def main():
    conn = psycopg2.connect(**PGSQL_CONFIG)

    store_dir = CLARKS["STORE_DIR"]

    print("🔁 遍历每个店铺目录并导入 TXT + SKU ID...")
    for store_folder in store_dir.iterdir():
        if store_folder.is_dir():
            stock_name = store_folder.name
            print(f"🏬 当前店铺: {stock_name}")

            # 导入 TXT 数据，绑定 stock_name
            import_txt_to_db(
                txt_dir=CLARKS["TXT_DIR"],
                brand="clarks",
                conn=conn,
                stock_name=stock_name
            )

            # 导入该目录下所有 Excel 中的 SKU ID
            import_skuid_from_store_excels(
                store_dir=store_folder,
                brand="clarks",
                conn=conn
            )

    print("✅ 所有店铺导入完毕")

if __name__ == "__main__":
    main()
