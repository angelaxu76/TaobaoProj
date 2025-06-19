from config import ECCO
from common_taobao.export_utils import export_discount_price_excel

if __name__ == "__main__":
    output_file = ECCO["DISCOUNT_PRICE_EXCEL"]
    export_discount_price_excel(ECCO, output_file)