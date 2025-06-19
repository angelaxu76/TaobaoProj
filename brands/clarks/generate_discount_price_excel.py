from common_taobao.core.export_discount_price import export_discount_excel
from config import CLARKS

export_discount_excel(
    txt_dir=CLARKS["TXT_DIR"],
    brand="clarks",
    output_excel=CLARKS["OUTPUT_DIR"] / "打折价格.xlsx"
)
