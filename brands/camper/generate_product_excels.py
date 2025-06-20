# ✅ 通用版本，可直接复用 prepare_utils_extended
import argparse
from common_taobao.prepare_utils_extended import generate_product_excels
from config import BRAND_CONFIG

def main():
    parser = argparse.ArgumentParser(description="生成商品发布 Excel 并拷贝图片")
    parser.add_argument("--brand", required=True, help="品牌名称")
    parser.add_argument("--store", required=True, help="淘宝店铺名称")
    args = parser.parse_args()

    config = BRAND_CONFIG[args.brand]
    generate_product_excels(config, args.store)

if __name__ == "__main__":
    main()
