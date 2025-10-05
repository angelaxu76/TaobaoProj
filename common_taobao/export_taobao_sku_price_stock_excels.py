from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from config import BRAND_CONFIG

def export_shop_sku_price_excels(
    brand: str,
    output_dir: str | Path,
    include_all: bool = False,   # False: 只导出有 skuid 的；True: 全部导出
) -> list[Path]:
    """
    为 BRAND_CONFIG[brand]['STORE_DIR'] 下每个店铺，导出一个 Excel（item_id, skuid, taobao_store_price）
    返回：导出的文件路径列表
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"不支持的品牌：{brand}")

    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    store_dir: Path = Path(cfg["STORE_DIR"])
    pg = cfg["PGSQL_CONFIG"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 收集店铺名：以目录名为准（与 stock_name 对应）
    shop_names = [p.name for p in store_dir.iterdir() if p.is_dir() and p.name != "clarks_default"]
    if not shop_names:
        print(f"⚠️ 未在 {store_dir} 发现任何店铺目录。")
        return []

    # SQL：只取三列，按店铺过滤；可选只导出有 skuid 的
    base_sql = f"""
        SELECT item_id, skuid, taobao_store_price
        FROM {table}
        WHERE stock_name = %s
    """
    if not include_all:
        base_sql += " AND skuid IS NOT NULL AND skuid <> ''"
    base_sql += " ORDER BY item_id NULLS LAST, skuid NULLS LAST;"

    out_files: list[Path] = []

    with psycopg2.connect(**pg) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for shop in shop_names:
                print(f"🔄 导出店铺：{shop}")
                cur.execute(base_sql, (shop,))
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=["item_id", "skuid", "taobao_store_price"])

                # 确保三列存在（即使为空）
                for col in ["item_id", "skuid", "taobao_store_price"]:
                    if col not in df.columns:
                        df[col] = None
                df = df[["item_id", "skuid", "taobao_store_price"]]

                df = df.rename(columns={
                    "item_id": "宝贝ID",
                    "skuid": "SKUID",
                    "taobao_store_price": "调整后价格"
                })

                # 导出
                out_path = output_dir / f"{brand}_{shop}_sku_price.xlsx"
                with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Sheet1")
                    # 简单设置列宽
                    ws = writer.sheets["Sheet1"]
                    ws.set_column(0, 0, 20)  # item_id
                    ws.set_column(1, 1, 20)  # skuid
                    ws.set_column(2, 2, 18)  # taobao_store_price

                print(f"✅ 导出完成：{out_path}（{len(df)} 行）")
                out_files.append(out_path)

    return out_files

def export_shop_sku_stock_excels(
    brand: str,
    output_dir: str | Path,
    include_all: bool = False,
) -> list[Path]:
    """
    为 BRAND_CONFIG[brand]['STORE_DIR'] 下每个店铺，导出一个 Excel（skuid, stock_count）
    返回：导出的文件路径列表
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"不支持的品牌：{brand}")

    cfg = BRAND_CONFIG[brand]
    table = cfg["TABLE_NAME"]
    store_dir: Path = Path(cfg["STORE_DIR"])
    pg = cfg["PGSQL_CONFIG"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shop_names = [p.name for p in store_dir.iterdir() if p.is_dir() and p.name != "clarks_default"]
    if not shop_names:
        print(f"⚠️ 未在 {store_dir} 发现任何店铺目录。")
        return []

    base_sql = f"""
        SELECT skuid, stock_count
        FROM {table}
        WHERE stock_name = %s
    """
    if not include_all:
        base_sql += " AND skuid IS NOT NULL AND skuid <> ''"
    base_sql += " ORDER BY skuid NULLS LAST;"

    out_files: list[Path] = []
    with psycopg2.connect(**pg) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for shop in shop_names:
                print(f"🔄 导出店铺库存：{shop}")
                cur.execute(base_sql, (shop,))
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=["skuid", "stock_count"])
                for col in ["skuid", "stock_count"]:
                    if col not in df.columns:
                        df[col] = None
                df = df[["skuid", "stock_count"]]

                df = df.rename(columns={
                    "skuid": "SKUID",
                    "stock_count": "调整后库存"
                })

                out_path = output_dir / f"{brand}_{shop}_sku_stock.xlsx"
                with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Sheet1")
                    ws = writer.sheets["Sheet1"]
                    ws.set_column(0, 0, 20)
                    ws.set_column(1, 1, 12)
                print(f"✅ 导出完成：{out_path}（{len(df)} 行）")
                out_files.append(out_path)
    return out_files

if __name__ == "__main__":
    # 示例：为 ECCO 导出到品牌默认 store 目录下的 output 子目录
    # 你也可以改成任何你想要的目录
    brand_name = "ecco"
    default_out = Path(BRAND_CONFIG[brand_name]["STORE_DIR"]) / "output_sku_price"
    export_shop_sku_price_excels(
        brand=brand_name,
        output_dir=default_out,
        include_all=False,   # 只导出有 skuid 的行
    )
