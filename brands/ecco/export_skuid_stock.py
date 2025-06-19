import psycopg2
from config import ECCO, PGSQL_CONFIG
from common_taobao.core.export_store_stock import export_store_stock_excel

def main():
    conn = psycopg2.connect(**PGSQL_CONFIG)

    store_dir = ECCO["STORE_DIR"]
    for store_folder in store_dir.iterdir():
        if store_folder.is_dir():
            stock_name = store_folder.name
            output_file = ECCO["OUTPUT_DIR"] / f"库存_{stock_name}.xlsx"
            print(f"📦 正在导出店铺: {stock_name}")
            export_store_stock_excel(
                brand="ecco",
                stock_name=stock_name,
                conn=conn,
                output_path=output_file
            )

if __name__ == "__main__":
    main()