import os
import shutil
import psycopg2
import pandas as pd
from pathlib import Path
from ecco.core.GenerateExcel import generate_excel_from_codes  # ⬅️ 替换为 ECCO 的版本
from config import PGSQL_CONFIG, ECCO

# ========== 路径配置 ==========
TXT_DIR = ECCO["TXT_DIR"]
IMAGE_DIR = ECCO["IMAGE_DIR"]
REPUB_DIR = ECCO["BASE"] / "repulibcation"

# ========== 拷贝商品图片 ==========
def copy_images_for_product(product_code, target_dir: Path):
    for img in IMAGE_DIR.glob(f"{product_code}_*.jpg"):
        shutil.copy(img, target_dir / img.name)

# ========== 获取符合发布条件的商品 ==========
def get_eligible_products_by_store(conn):
    store_dict = {}
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT stock_name FROM ecco_inventory")
        store_names = [row[0] for row in cursor.fetchall()]

    for store in store_names:
        query = """
            SELECT product_name, gender
            FROM ecco_inventory
            WHERE stock_name = %s AND is_published = false
        """
        df = pd.read_sql(query, conn, params=(store,))
        grouped = df.groupby("product_name")
        valid_codes = []
        gender_map = {}

        for code, group in grouped:
            if group.shape[0] >= 3 and group['gender'].iloc[0].lower() in ['men', 'women']:
                valid_codes.append(code)
                gender_map[code] = group['gender'].iloc[0].lower()

        store_dict[store] = {"codes": valid_codes, "gender": gender_map}
    return store_dict

# ========== 主函数 ==========
def generate_product_excels_main():
    with psycopg2.connect(**PGSQL_CONFIG) as conn:
        all_store_data = get_eligible_products_by_store(conn)

        for store, data in all_store_data.items():
            print(f"\n📦 ECCO 处理店铺：{store}，符合商品数：{len(data['codes'])}")
            store_dir = REPUB_DIR / store
            image_dir = store_dir / "images"
            store_dir.mkdir(parents=True, exist_ok=True)
            image_dir.mkdir(parents=True, exist_ok=True)

            men_codes = [code for code in data['codes'] if data['gender'][code] == 'men']
            women_codes = [code for code in data['codes'] if data['gender'][code] == 'women']

            if women_codes:
                out_file = store_dir / "女款发布.xlsx"
                generate_excel_from_codes(women_codes, str(out_file))

            if men_codes:
                out_file = store_dir / "男款发布.xlsx"
                generate_excel_from_codes(men_codes, str(out_file))

            for code in data['codes']:
                copy_images_for_product(code, image_dir)

    print("\n🎉 ECCO 所有店铺商品已整理完毕，可执行 changeImageSize.py 压缩 images 文件夹")

if __name__ == "__main__":
    generate_product_excels_main()
