"""
跨店铺差商品报告（先运行 run_import_data 导入三个店铺数据）

规则：价格高 且 无访问 且 无折扣（参数见 store_config.py 的 BAD_*）
输出到 CROSS_STORE_EXPORT_DIR：
  cross_store_bad_products_YYYYMMDD.xlsx
    待删除          一行一个编码：鲸芽渠道产品ID、各店淘宝商品ID、指标、原因
    鲸芽渠道产品ID  一行一个渠道产品ID
    差但有折扣_保留 / 库存表未找到
  jingya_channel_product_ids_to_delete_YYYYMMDD.txt   待删除商品的鲸芽渠道产品ID，一行一个
并按 BAD_WRITE_BLOCKLIST 把待删除商品写入发布黑名单（数据库表 publish_blocklist，见 ops/blocklist/）。
"""
from analytics.ingest.export_cross_store_bad_products import BadProductRule, build_bad_product_report, write_report
from analytics.pipeline.store_config import (
    CROSS_STORE_EXPORT_DIR, get_active_stores,
    BAD_WINDOW_DAYS, BAD_MIN_PUBLISH_DAYS, BAD_METRIC, BAD_METRIC_MAX,
    BAD_MAX_PAY_QTY, BAD_MAX_CART_QTY, BAD_MAX_FAV_CNT,
    BAD_WRITE_BLOCKLIST, BAD_MIN_PRICE_BY_BRAND,
)
from common.publication.publish_blocklist import upsert_blocklist


def to_blocklist_rows(to_delete) -> list[dict]:
    return [
        {
            "product_code": r["product_code"],
            "brand": r["brand"],
            "original_price_gbp": r["original_price_gbp"],
            "discount_price_gbp": r["discount_price_gbp"],
            "discount_rate": r["discount_rate"],
            "reason": r["reason"],
            "source": "cross_store_bad",
            "release_on_discount": True,   # 供应商打折后自动解除拦截，可重新发布
        }
        for _, r in to_delete.iterrows()
    ]


if __name__ == "__main__":
    stores = get_active_stores()
    rule = BadProductRule(
        stores=[s.store_name for s in stores],
        store_labels={s.store_name: s.folder for s in stores},
        window_days=BAD_WINDOW_DAYS,
        min_publish_days=BAD_MIN_PUBLISH_DAYS,
        metric=BAD_METRIC,
        metric_max=BAD_METRIC_MAX,
        max_pay_qty=BAD_MAX_PAY_QTY,
        max_cart_qty=BAD_MAX_CART_QTY,
        max_fav_cnt=BAD_MAX_FAV_CNT,
        min_price_by_brand=BAD_MIN_PRICE_BY_BRAND,
    )
    print(f"店铺：{'、'.join(str(s) for s in stores)}")
    print(f"规则（三条同时满足）：")
    print(f"  价格高：一口价 > {rule.min_price_by_brand or '不限'}")
    print(f"  无访问：发布满 {rule.min_publish_days} 天，近 {rule.window_days} 天所有店 {rule.metric} 合计 < {rule.metric_max}，"
          f"成交 <= {rule.max_pay_qty}，加购 <= {rule.max_cart_qty}，收藏 <= {rule.max_fav_cnt}")
    print(f"  无折扣：供应商端未打折")

    result = build_bad_product_report(rule)
    xlsx, txt = write_report(result, CROSS_STORE_EXPORT_DIR)

    to_delete = result["to_delete"]
    print(f"日报截止：{result['end_date']}，共 {result['codes_total']} 个编码")
    print(f"  待删除：{len(to_delete)}")
    if not to_delete.empty:
        print(to_delete.groupby("brand").size().to_string())
    print(f"  价格高+无访问 但有折扣（保留）：{len(result['kept_discounted'])}")
    print(f"  库存表未找到（未处理）：{len(result['not_found'])}")
    print(f"  鲸芽渠道产品ID：{len(result['jingya_ids'])} 个")
    print(f"✅ 报告：{xlsx}")
    print(f"✅ 鲸芽渠道产品ID：{txt}")

    if BAD_WRITE_BLOCKLIST and not to_delete.empty:
        upsert_blocklist(to_blocklist_rows(to_delete))
    elif not BAD_WRITE_BLOCKLIST:
        print("ℹ️ BAD_WRITE_BLOCKLIST = False，未写入发布黑名单")
