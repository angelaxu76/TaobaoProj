from pathlib import Path
import pandas as pd
from config import TOAST, resolve_shared_path
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.export.export_gender_split_excel import export_gender_split_excel
from channels.jingya.export.generate_publication_excel_outerwear import generate_publication_excels_clothing
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from brands.toast.collect_product_links import toast_get_links
from brands.toast.fetch_product_info import toast_fetch_all
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_for_brand
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand
from channels.jingya.maintenance.generate_empty_product_links_for_brand import generate_empty_product_links_for_brand


STORE_PRICE_INPUT_DIR = resolve_shared_path(r"\\vmware-host\Shared Folders\shared\toast\store_prices")
STORE_PRICE_OUTPUT_DIR = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\toast\store_prices")
PUBLICATION_PRICE_DIR = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\toast\publication_prices")
BLACKLIST_EXCEL_FILE = resolve_shared_path(r"\\vmware-host\Shared Folders\shared\toast\exclude.xlsx")


def ensure_default_inputs():
    """
    新品牌尚未在鲸芽发布商品：按其他品牌的目录结构建好默认目录和空 Excel。
    - GEI_DIR：鲸芽导出 GEI@sales_catalogue_export@*.xlsx 放这里；为空时相关步骤自动跳过
    - store_prices：各淘宝店铺导出的价格 Excel；为空时改价步骤自动跳过
    - exclude.xlsx：黑名单（仅表头 商品编码），等同于不启用黑名单
    """
    for d in (TOAST["GEI_DIR"], STORE_PRICE_INPUT_DIR, STORE_PRICE_OUTPUT_DIR, PUBLICATION_PRICE_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)

    blacklist = Path(BLACKLIST_EXCEL_FILE)
    if not blacklist.exists():
        pd.DataFrame(columns=["商品编码"]).to_excel(blacklist, index=False)
        print(f"  - 已创建空黑名单：{blacklist}")


def main():
    print("\n🟡 Step: 0️⃣ 准备默认目录和空 Excel（GEI / 店铺价格 / 黑名单）")
    ensure_default_inputs()

    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(TOAST)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    toast_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    toast_fetch_all()

    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    # 与 LINKS_FILE 同目录，toast_fetch_all 会读同目录下的 links_meta.json 补性别
    missing_product_link = TOAST["BASE"] / "publication" / "missing_product_links.txt"
    generate_missing_links_for_brand("toast", str(missing_product_link))
    if missing_product_link.exists() and missing_product_link.stat().st_size > 0:
        toast_fetch_all(urls_file=missing_product_link)
    else:
        print("  - 无缺失商品，跳过")

    print("\n🟡 Step: 3️⃣ 找出TXT中价格/库存全空的商品（网络原因导致抓取失败），重新抓一遍")
    empty_product_link = generate_empty_product_links_for_brand("toast")
    if empty_product_link.exists() and empty_product_link.stat().st_size > 0:
        toast_fetch_all(urls_file=empty_product_link)
    else:
        print("  - 无空数据商品，跳过")

    print("\n🟡 Step: 4️⃣ TXT导入数据库 -----将各个商品的TXT中信息导入到数据库中")
    import_txt_to_db_supplier("toast")

    print("\n🟡 Step: 5️⃣ 通过解析鲸芽导出的Excel，将鲸芽侧相关的商品ID和SKU信息导入数据库")
    insert_jingyaid_to_db("toast")

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("toast")

    print("\n🟡 Step: 6️⃣ 导出男装商品列表，女装商品列表，用于更新尺码库存数据库版")
    export_gender_split_excel("toast")

    print("\n🟡 Step: 6️⃣ 鲸芽侧更新价格和库存------")
    stock_dest_excel_folder = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\input")
    export_stock_excel("toast", stock_dest_excel_folder)

    print("\n🟡 Step: 6️⃣ 导出价格用于更新")
    export_jiangya_channel_prices("toast", PUBLICATION_PRICE_DIR, chunk_size=200)

    print("\n🟡 Step: 6️⃣为新品创建excel用于鲸芽侧发布（服装全品类）")
    generate_publication_excels_clothing("toast", all_categories=True)

    print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    export_low_stock_for_brand("toast", threshold=5)

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="toast",
        input_dir=STORE_PRICE_INPUT_DIR,
        output_dir=STORE_PRICE_OUTPUT_DIR,
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False,  # 不丢行，查不到的价格留空
        blacklist_excel_file=BLACKLIST_EXCEL_FILE,
        allow_blacklist_price_increase=True,  # 开关：True=黑名单商品仅涨价可调、降价不动；False=涨降价都不动
    )

    print("\n✅ TOAST pipeline 完成")

if __name__ == "__main__":
    main()
