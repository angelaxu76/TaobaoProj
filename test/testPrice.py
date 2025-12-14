from pathlib import Path
from common_taobao.core.price_utils import calculate_jingya_prices

def main():
    untaxed, retail = calculate_jingya_prices(113,7,9.7)


    print(f"📂 鲸芽价格: \n{untaxed}")
    print(f"📂 淘宝价格: \n{retail}")


if __name__ == "__main__":
    main()
