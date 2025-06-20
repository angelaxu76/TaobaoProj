from common_taobao.core.export_discount_price import export_discount_excel
from config import GEOX

export_discount_excel(
    txt_dir=GEOX["TXT_DIR"],
    brand="geox",
    output_excel=GEOX["OUTPUT_DIR"] / "打折价格.xlsx"
)