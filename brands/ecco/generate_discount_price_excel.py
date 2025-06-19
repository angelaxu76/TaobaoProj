from config import ECCO
from common_taobao.core.export_discount_price import export_discount_excel

export_discount_excel(
    txt_dir=ECCO ["TXT_DIR"],
    brand="ECCO",
    output_excel=ECCO["OUTPUT_DIR"] / "打折价格.xlsx"
)