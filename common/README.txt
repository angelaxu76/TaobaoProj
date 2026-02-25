【common/ — 通用引擎层（原 common_taobao）】
规则：跨品牌、跨渠道的工具函数，不含任何品牌特有逻辑或渠道 Excel 生成逻辑。

  core/         →  价格计算、尺码标准化、类目分类、标题生成、图片工具、DB导入、Selenium工具
  image/        →  图片检查、按编码分组
  ingest/       →  TXT 解析器（parse_txt_to_record）、通用 TXT → DB
  maintenance/  →  备份与清空目录（backup_and_clear_brand_dirs）
  pricing/      →  定价相关通用逻辑
  publication/  →  发布用工具（生成HTML详情页、价格Excel、下架标记、prepare_utils等）
  text/         →  淘宝标题生成、风格/系列关键词提取
