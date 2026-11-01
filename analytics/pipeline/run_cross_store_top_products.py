"""
跨店铺优质商品报告（直通车推广候选，先运行 run_import_data 导入三个店铺数据）

输出到 CROSS_STORE_EXPORT_DIR：
  cross_store_top_products_YYYYMMDD.xlsx   全部品牌 / 各品牌 / ID_各店铺 / 规则说明
规则参数见 store_config.py 的 TOP_*。
"""
from analytics.ingest.export_cross_store_top_products import TopProductRule, build_top_product_report, write_report
from analytics.pipeline.store_config import (
    CROSS_STORE_EXPORT_DIR, get_active_stores,
    TOP_WINDOW_DAYS, TOP_SCORE_WEIGHTS, TOP_MIN_PAGEVIEWS, TOP_MIN_CART, TOP_MIN_PAY_QTY,
    TOP_MIN_STORE_CNT, TOP_N_PER_BRAND,
)


if __name__ == "__main__":
    stores = get_active_stores()
    rule = TopProductRule(
        stores=[s.store_name for s in stores],
        store_labels={s.store_name: s.folder for s in stores},
        window_days=TOP_WINDOW_DAYS,
        weights=TOP_SCORE_WEIGHTS,
        min_pageviews=TOP_MIN_PAGEVIEWS,
        min_cart=TOP_MIN_CART,
        min_pay_qty=TOP_MIN_PAY_QTY,
        min_store_cnt=TOP_MIN_STORE_CNT,
        top_n_per_brand=TOP_N_PER_BRAND,
    )
    print(f"店铺：{'、'.join(str(s) for s in stores)}")
    print(f"规则：近 {rule.window_days} 天合计，浏览 >= {rule.min_pageviews}，加购 >= {rule.min_cart}，"
          f"成交 >= {rule.min_pay_qty}，上架店铺 >= {rule.min_store_cnt}，每品牌前 {rule.top_n_per_brand}")
    print(f"得分权重：{rule.weights}")

    result = build_top_product_report(rule)
    xlsx = write_report(result, rule, CROSS_STORE_EXPORT_DIR)

    top = result["top"]
    print(f"日报区间：{result['start_date']} ~ {result['end_date']}，共 {result['codes_total']} 个编码，"
          f"达到门槛 {result['qualified_total']} 个，导出 {len(top)} 个")
    if not top.empty:
        print(top.groupby("brand").size().to_string())
    print(f"✅ 报告：{xlsx}")
