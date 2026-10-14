"""
跨店铺差商品报告（先运行 run_import_data 导入三个店铺数据）

输出到 CROSS_STORE_EXPORT_DIR：
  cross_store_bad_products_YYYYMMDD.xlsx       待删除 / 鲸芽ID / 差但有折扣_保留 / 库存表未找到 / 店铺明细
  jingya_channel_product_ids_to_delete_YYYYMMDD.txt   待删除商品的鲸芽渠道产品ID，一行一个
并按 BAD_WRITE_BLOCKLIST 把待删除商品写入发布黑名单。规则参数见 store_config.py 的 BAD_*。
"""
from analytics.ingest.export_cross_store_bad_products import BadProductRule, build_bad_product_report, write_report
from analytics.pipeline.store_config import (
    CROSS_STORE_EXPORT_DIR, get_active_stores,
    BAD_WINDOW_DAYS, BAD_MIN_PUBLISH_DAYS, BAD_METRIC, BAD_METRIC_MAX, BAD_MAX_PAY_QTY,
    BAD_REQUIRE_ALL_STORES, BAD_WRITE_BLOCKLIST,
)
from common.publication.publish_blocklist import append_to_blocklist


def to_blocklist_rows(to_delete) -> list[dict]:
    return [
        {
            "商品编码": r["product_code"],
            "品牌": r["brand"],
            "原价": r["original_price_gbp"],
            "打折后价格": r["discount_price_gbp"],
            "折扣": r["discount_rate"],
            "无访问被删除次数": 1,
            "原因": r["reason"],
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
        require_all_stores=BAD_REQUIRE_ALL_STORES,
    )
    print(f"店铺：{'、'.join(str(s) for s in stores)}")
    print(f"规则：发布满 {rule.min_publish_days} 天，近 {rule.window_days} 天 {rule.metric} < {rule.metric_max}，"
          f"成交 <= {rule.max_pay_qty}，{'须全部店铺上架' if rule.require_all_stores else '上架店铺都差即可'}")

    result = build_bad_product_report(rule)
    xlsx, txt = write_report(result, CROSS_STORE_EXPORT_DIR)

    to_delete = result["to_delete"]
    print(f"日报截止：{result['end_date']}，共 {result['codes_total']} 个编码")
    print(f"  待删除（差且未打折）：{len(to_delete)}")
    print(f"  差但有折扣（保留）：{len(result['kept_discounted'])}")
    print(f"  库存表未找到（未处理）：{len(result['not_found'])}")
    print(f"  鲸芽渠道产品ID：{len(result['jingya_ids'])} 个")
    if not to_delete.empty:
        print(to_delete.groupby("brand").size().to_string())
    print(f"✅ 报告：{xlsx}")
    print(f"✅ 鲸芽ID：{txt}")

    if BAD_WRITE_BLOCKLIST and not to_delete.empty:
        append_to_blocklist(to_blocklist_rows(to_delete))
    elif not BAD_WRITE_BLOCKLIST:
        print("ℹ️ BAD_WRITE_BLOCKLIST = False，未写入发布黑名单")
