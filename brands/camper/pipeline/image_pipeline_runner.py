"""
Camper 商品图流水线已拆成 4 个独立脚本（同目录下），依次运行：

  1. image_pipeline_step1_download_and_square.py
     下载图片 -> 变成正方形（不再调用 image_defender_with_flip.batch_process_images
     的抖动+翻转防指纹步骤，改用 AI 生成新视角图代替）

  2a. image_pipeline_step2_upload_to_r2.py
      人工看一眼 step1 处理结果没问题后，把 IMAGE_CUTTER 传到 R2

  2b. image_pipeline_step2_ai_rotate.py
      调 AI 对 R2 上的图做视角旋转，结果存到 IMAGE_ROTATED

  3. image_pipeline_step3_merge_and_html.py
     合并 IMAGE_CUTTER + IMAGE_ROTATED 两个目录的图 -> 生成详情页/首页 HTML 和图片

拆开是因为 2a 之前通常需要人工检查图片，不适合跟其他步骤自动连着跑。
"""
