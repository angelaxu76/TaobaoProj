from config import CAMPER
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_channel_products

def main():
    output_excel_path_str = r"C:\Users\martin\Desktop\remove_geox.xlsx"

    export_low_stock_channel_products(
    brand="geox",
    stock_threshold=7,
    output_excel_path=r"C:\Users\martin\Desktop\remove_geox.xlsx",
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )


    export_low_stock_channel_products(
    brand="clarks_jingya",
    stock_threshold=7,
    output_excel_path=r"C:\Users\martin\Desktop\remove_clarks.xlsx",
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="ecco",
    stock_threshold=7,
    output_excel_path=r"C:\Users\martin\Desktop\remove_ecco.xlsx",
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="camper",
    stock_threshold=8,
    output_excel_path=r"C:\Users\martin\Desktop\remove_camper.xlsx",
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )

    export_low_stock_channel_products(
    brand="barbour",
    stock_threshold=7,
    output_excel_path=r"C:\Users\martin\Desktop\remove_barbour.xlsx",
    max_allowed_size_count=2,  # 默认就是 2，不写也可以
    )




    print(f"output complete..........")
if __name__ == "__main__":
    main()
