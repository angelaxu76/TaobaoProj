【analytics/ — 商品指标分析层（原 product_analytics）】
规则：生意参谋数据导入、商品表现报表导出。

  database/  →  建表 SQL（catalog_items、product_metrics_daily 等）
  ingest/    →  从 Excel 导入商品指标数据 / 生成差商品报表
  pipeline/  →  运行入口（run_import_data.py、run_export_data.py）
