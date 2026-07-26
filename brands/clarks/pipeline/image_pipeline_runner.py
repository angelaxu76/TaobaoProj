"""
Clarks 商品图流水线已拆成 4 个独立脚本（同目录下），依次运行：

  1. image_pipeline_step1_download.py
     下载图片（不再调用 batch_process_images 的抖动+翻转防指纹步骤，改用
     AI 生成新视角图代替）

     -> 手动去 CLARKS["IMAGE_DOWNLOAD"] 删掉不需要的模特图/生活场景图 <-

  2a. image_pipeline_step2_rename_and_upload_to_r2.py
      按新顺序重命名（1,6,2,3,5,4,7,8,9 -> 1,2,3,4,5,6,7,8,9），再把
      IMAGE_DOWNLOAD 传到 R2

  2b. image_pipeline_step2_ai_rotate.py
      调 AI 对 R2 上的图做视角旋转，结果存到 IMAGE_ROTATED

  3. image_pipeline_step3_crop_merge_and_html.py
     裁剪 IMAGE_DOWNLOAD -> IMAGE_CUTTER，拷贝到 IMAGE_PROCESS（供 HTML 生成
     找封面图）和 document 目录，合并 IMAGE_CUTTER + IMAGE_ROTATED 两个目录的
     图，生成详情页/首页 HTML 和图片

拆开是因为下载完之后需要人工删模特图，删完才能重命名，重命名之后才适合
上传/旋转，不适合几步自动连着跑。

重命名会影响 cfg/brands/clarks.py 里 IMAGE_PRIORITY / IMAGE_FIRST_PRIORITY /
IMAGE_DES_PRIORITY 这几个优先级列表指向的实际图片，已经按新编号翻译过，
仍然对应原来同一批照片。
"""
