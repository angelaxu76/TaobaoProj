
import pandas as pd

def export_store_stock_excel(brand, stock_name, conn, output_path):
    table_name = f"{brand}_inventory"
    cursor = conn.cursor()

    query = f"""
        SELECT skuid, stock_status
        FROM {table_name}
        WHERE stock_name = %s AND skuid IS NOT NULL
    """

    cursor.execute(query, (stock_name,))
    rows = cursor.fetchall()

    result = []
    for skuid, stock_status in rows:
        quantity = 3 if stock_status == "有货" else 0
        result.append([skuid, quantity])

    df = pd.DataFrame(result, columns=["SKUID", "调整后库存"])
    df.to_excel(output_path, index=False)
    print(f"✅ 库存导出完成: {output_path}")
