【brands/ — 品牌数据采集层】
规则：只放品牌网站的抓取脚本和品牌特有逻辑，不放渠道操作。
每个品牌子目录结构：
  fetch_*.py / collect_product_links.py  →  品牌网站抓取
  download_product_images.py             →  图片下载
  pipeline/prepare_jingya_listing.py     →  该品牌完整上架流程入口
  core/                                  →  品牌特有匹配/解析逻辑（如 barbour）
  database/                              →  建表 SQL
  legacy/                                →  旧实现（对照/回滚用）
