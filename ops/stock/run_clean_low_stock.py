from config import CAMPER, DESKTOP_DIR
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_channel_products
from brands.barbour.pipeline.session_config import ONE_SIZE_PREFIXES

def main():
    export_low_stock_channel_products(
    brand="geox",
    stock_threshold=7,
    output_excel_path=str(DESKTOP_DIR / "remove_geox.xlsx"),
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )


    export_low_stock_channel_products(
    brand="clarks",
    stock_threshold=7,
    output_excel_path=str(DESKTOP_DIR / "remove_clarks.xlsx"),
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="ecco",
    stock_threshold=7,
    output_excel_path=str(DESKTOP_DIR / "remove_ecco.xlsx"),
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="camper",
    stock_threshold=8,
    output_excel_path=str(DESKTOP_DIR / "remove_camper.xlsx"),
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="barbour",
    stock_threshold=7,
    output_excel_path=str(DESKTOP_DIR / "remove_barbour.xlsx"),
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    one_size_prefixes=ONE_SIZE_PREFIXES,  # 帽子/围巾/包等均码商品只在无货时导出
    )




    print(f"output complete..........")
if __name__ == "__main__":
    main()
