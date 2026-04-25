from pathlib import Path
from common.pricing.price_utils import calculate_jingya_prices

def main():
    untaxed, retail = calculate_jingya_prices(73,7,9.3)


    print(f"📂 鲸芽价格: \n{untaxed}")
    print(f"📂 淘宝价格折扣前: \n{retail}")

    print(f"📂 淘宝价格折扣后: \n{retail*0.85}")


if __name__ == "__main__":
    main()
