from datetime import datetime
from pathlib import Path

from config import BARBOUR
from channels.jingya.check.channel_price_check import (
    check_jingya_price_mismatch,
    check_taobao_margin_safety,
)

def barbour_price_checks():
    # === 1. 鲸芽价同步检查 ===
    jingya_excel_path = r"D:\TB\Products\barbour\document\GEI@sales_catalogue_export@251031074615@9584.xlsx"
    ts1 = datetime.now().strftime("%Y%m%d_%H%M%S")
    out1 = Path(BARBOUR["BASE"]) / "document" / "price_check" / f"barbour_price_diff_{ts1}.xlsx"
    out1.parent.mkdir(parents=True, exist_ok=True)

    check_jingya_price_mismatch(
        brand="barbour",
        jingya_excel_path=jingya_excel_path,
        output_report_path=str(out1),
        tolerance=0.5,
        excel_skuid_col="skuID",
        excel_price_col="通用渠道价格（未税）",
        excel_title_col="渠道产品名称",
    )

    # === 2. 淘宝倒挂风险检查 ===
    taobao_excel_path = r"D:\TB\Products\barbour\document\store\英国伦敦代购.xlsx"
    ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
    out2 = Path(BARBOUR["BASE"]) / "document" / "price_check" / f"barbour_taobao_risk_英国伦敦代购_{ts2}.xlsx"
    out2.parent.mkdir(parents=True, exist_ok=True)

    check_taobao_margin_safety(
        brand="barbour",
        taobao_excel_path=taobao_excel_path,
        output_report_path=str(out2),
        safety_multiplier=1.4,
        excel_spec_col="sku规格",
        excel_price_col="sku销售价",
        excel_title_col="宝贝标题",  # 如果淘宝excel有标题列，可以填列名，比如 "商品名称"
    )

if __name__ == "__main__":
    barbour_price_checks()
