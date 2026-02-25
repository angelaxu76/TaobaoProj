import argparse
from common.prepare_utils import get_publishable_product_codes
from config import BRAND_CONFIG

def main():
    parser = argparse.ArgumentParser(description="查找待发布商品编码")
    parser.add_argument("--brand", required=True, help="品牌名称，例如 clarks")
    parser.add_argument("--store", required=True, help="淘宝店铺名称，例如 五小剑")
    args = parser.parse_args()

    config = BRAND_CONFIG[args.brand]
    codes = get_publishable_product_codes(config, args.store)

    print(f"✅ 共找到 {len(codes)} 个待发布商品编码")
    for code in codes:
        print(code)

if __name__ == "__main__":
    main()
