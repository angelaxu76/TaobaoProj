
import os
import pandas as pd
import psycopg2
from pathlib import Path
from config import PGSQL_CONFIG

# 生意参谋运营字段映射
COLUMN_MAP = {
    "主商品ID": "item_id",
    "商品访客数": "visitor_count",
    "商品浏览量": "page_views",
    "平均停留时长（秒）": "avg_stay_time_seconds",
    "商品收藏人数": "favorite_count",
    "商品加购件数": "cart_count",
    "下单件数": "order_count",
    "下单转化率": "order_conversion_rate",
    "搜索引导访客数": "search_visitors",
    "搜索引导支付买家数": "search_buyers"
}

def clean_int(val):
    try:
        return int(str(val).replace(",", "").strip())
    except:
        return None

def clean_percent(val):
    try:
        return round(float(str(val).replace("%", "").strip()), 2)
    except:
        return None

def update_sycm_data(base_dir: str):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()

    base = Path(base_dir)
    for file in base.glob("*.xlsx"):
        try:
            df = pd.read_excel(file, skiprows=4)
            if "主商品ID" not in df.columns:
                print(f"⚠️ 跳过文件（字段缺失）: {file.name}")
                continue

            for _, row in df.iterrows():
                item_id = str(row.get("主商品ID")).strip()
                if not item_id:
                    continue

                update_data = {
                    "visitor_count": clean_int(row.get("商品访客数")),
                    "page_views": clean_int(row.get("商品浏览量")),
                    "avg_stay_time_seconds": clean_int(row.get("平均停留时长（秒）")),
                    "favorite_count": clean_int(row.get("商品收藏人数")),
                    "cart_count": clean_int(row.get("商品加购件数")),
                    "order_count": clean_int(row.get("下单件数")),
                    "order_conversion_rate": clean_percent(row.get("下单转化率")),
                    "search_visitors": clean_int(row.get("搜索引导访客数")),
                    "search_buyers": clean_int(row.get("搜索引导支付买家数"))
                }

                assignments = ", ".join([f"{k} = %s" for k in update_data])
                sql = f"UPDATE all_inventory SET {assignments} WHERE item_id = %s"

                try:
                    cur.execute(sql, list(update_data.values()) + [item_id])
                except Exception as e:
                    print(f"❌ 更新失败 item_id={item_id}: {e}")
                    conn.rollback()

            conn.commit()
            print(f"✅ 完成更新: {file.name}")

        except Exception as e:
            print(f"❌ 读取失败: {file.name}, 错误: {e}")

    cur.close()
    conn.close()
    print("🎉 所有生意参谋数据更新完成")

# 示例用法（正式运行时取消注释）
# update_sycm_data("D:/TB/Products/all/sycm")
