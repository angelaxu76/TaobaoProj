# helper 目录说明

helper 是我们电商流水线的“素材/数据处理工坊”。

它分成四个子模块：

## 1. helper/image
图片生产线相关脚本。包括：
- 商品图标准化（裁边、补白成方图、加编码、加水印、防盗）
- 图片压缩、尺寸限制、批量合图等，用于淘宝/鲸芽/菜鸟平台的图片规范
- 示例文件：
  - trim_sides_batch.py          # 去四周留白
  - crop_to_square.py            # 裁剪/补齐成正方形
  - expand_square_add_code.py    # 方图 + 打上商品编码/货号
  - merge_product_images.py      # 多张图拼成长图/九宫格
  - image_defender.py            # 防盗图（加水印/扰动）
  - resize_images_batch.py       # 批量限制尺寸
  - resize_images_to_1500_batch.py
  - webp_to_jpg.py / avif_to_jpg.py
  - jpg_to_pdf.py (*说明：运营/客服用，如果后续不参与自动发布可以移到 tools*)

## 2. helper/html
HTML → 图片 的物料生成脚本。包括：
- 根据抓取到的商品信息生成中文详情卡 HTML
- 批量把 HTML 渲染成 PNG/JPG，作为宝贝详情图/素材图使用
- 示例文件：
  - html_image_pipeline.py
  - html_to_png_batch.py
  - html_to_png_multithread.py

## 3. helper/excel
运营 Excel 处理辅助脚本。包括：
- 拆分大表（平台允许1000行以内等限制）
- 从鲸芽导出的表格做二次清洗
- 找重复编码、导出折扣候选等
- 示例文件：
  - split_excel_by_rows.py
  - check_gei_duplicates.py
  - export_discount_candidates_excel.py
  - find_duplicate_codes_excel.py
  - get_taobao_ids_from_discount_list.py

这些脚本有些会被 pipeline 调用（如检查重复、按行拆分），有些是人工运营辅助。

## 4. helper/txt
上新批次的 ID 列表管理：
- 清理掉“已经处理过的编码”，避免重复上传
- 清理掉无效/下架条目
- 示例文件：
  - remove_processed_ids.py
  - remove_sale_id.py

这些通常是手工跑来准备下一批上新的输入清单。

---

## 使用约定
- 如果脚本是发布链路中**必须的**，就留在 helper，并确保它能被 import。
- 如果脚本只是临时导出报告、打包证据给客服、人工复查，那应该放在 tools/ 目录，不应该被 pipeline import。
