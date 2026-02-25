【channels/ — 渠道操作层】
规则：所有写入/读取渠道（鲸芽/淘宝）的代码都在这里，不放品牌特有抓取逻辑。

channels/jingya/
  ingest/       →  将数据导入鲸芽 DB（TXT/Excel → DB）
  export/       →  从 DB 生成鲸芽/淘宝需要的 Excel
  pricing/      →  折扣策略、价格生成、SKU 价格库存导出
  maintenance/  →  维护任务（低库存下架、渠道ID查询、绑定ID提取）
  check/        →  校验（价差检查、排除列表处理）
  cainiao/      →  菜鸟/鲸芽物流相关 Excel 生成（HS Code、绑定、发货更新）
  pipeline/     →  鲸芽上架流程共享步骤库（jingya_listing_pipeline.py）

channels/taobao/
  utils/        →  淘宝渠道通用工具
  legacy/       →  旧版淘宝渠道脚本
