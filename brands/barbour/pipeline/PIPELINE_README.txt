================================================================================
  Barbour Pipeline 脚本执行顺序说明
  文件位置：brands/barbour/pipeline/
================================================================================

【总体流程概览】

  A. 抓取供应商数据  →  B. 导入数据库  →  C. 构建库存  →  D. 导出库存/价格 Excel
  E. 图片下载处理   →  F. 选图/水印/分类  →  G. HTML 详情图  →  H. 生成发布 Excel

================================================================================
  阶段 A：抓取供应商商品信息
  脚本：crawl_supplier_info.py
================================================================================

  步骤 0（可选）：清空 TXT + 发布目录（备份旧数据）
    backup_and_clear_brand_dirs(BARBOUR)

  步骤 1：获取各供应商商品链接（写入 links 文件）
    barbour_get_links()                      ← Barbour 官网
    outdoorandcountry_fetch_and_save_links() ← Outdoor & Country
    allweathers_get_links()
    houseoffraser_get_links()
    collect_terraces_links()
    philipmorris_get_links()
    cho_get_links()
    # very_get_links()                        ← 暂时停用

  步骤 2：按链接抓取商品详情 → 写入 TXT 文件
    barbour_fetch_info()
    outdoorandcountry_fetch_info(max_workers=1)  ← 需 undetected_chromedriver（Cloudflare）
    allweathers_fetch_info(7)
    houseoffraser_fetch_info(max_workers=7, headless=False)
    terraces_fetch_info(max_workers=7)
    philipmorris_fetch_info(max_workers=7)
    cho_fetch_info(max_workers=7)

  步骤 3（可选）：移除 TXT 目录中无 Barbour 编码的文件
    move_non_barbour_files(houseoffraser/TXT, houseoffraser/TXT.bk)
    move_non_barbour_files(cho/TXT, cho/TXT.bk)
    move_non_barbour_files(philipmorris/TXT, philipmorris/TXT.bk)
    move_non_barbour_files(terraces/TXT, terraces/TXT.bk)

================================================================================
  阶段 B：将 TXT 导入数据库
  脚本：db_import_txt_products_offers.py
================================================================================

  步骤 3：TXT → barbour_products 表（商品基础信息）
    batch_import_txt_to_barbour_product("barbour")
    batch_import_txt_to_barbour_product("outdoorandcountry")
    batch_import_txt_to_barbour_product("allweathers")
    batch_import_txt_to_barbour_product("philipmorris")
    batch_import_txt_to_barbour_product("cho")
    # batch_import_txt_to_barbour_product("houseoffraser")  ← 暂停用

  步骤 4：TXT → barbour_offers 表（各供应商库存/价格）
    import_txt_for_supplier("barbour", False)
    import_txt_for_supplier("outdoorandcountry", False)
    import_txt_for_supplier("allweathers", False)
    import_txt_for_supplier("houseoffraser", False)
    import_txt_for_supplier("very", False)
    import_txt_for_supplier("terraces", False)
    import_txt_for_supplier("philipmorris", False)
    import_txt_for_supplier("cho", False)

================================================================================
  阶段 B2（可选）：处理无编码商品（houseoffraser 等来源）
  脚本：db_import_match_unmatched_codes.py
================================================================================

  1. 导入无编码 TXT 到候选池：
       import_from_txt("houseoffraser")

  2. 导出候选池 Excel（product_code 列为空）：
       export_candidates_excel("barbour_candidates.xlsx", True)

  3. 【人工操作】在 Excel 里填写 product_code

  4. 回填编码到 barbour_products + TXT 文件重命名：
       import_codes_from_excel("barbour_candidates_xxx.xlsx")
       backfill_product_codes_to_txt("houseoffraser")

================================================================================
  阶段 C：构建供应商映射 & Inventory
  脚本：db_build_supplier_map_and_inventory.py
================================================================================

  根据需要选择对应场景（修改脚本底部的 MODE 参数）：

  场景 1 - full_rebuild（全新重建）
    清空 inventory → 插入鲸芽已发布商品 → 写入 jingya_id → 计算 supplier_map
    → 单一最佳供货商回填 inventory → 10% 价格带库存合并

  场景 2 - refresh_inventory（供应商数据更新后刷新）
    清空 inventory → 插入鲸芽已发布商品 → 写入 jingya_id
    → 单一最佳供货商回填 → 10% 价格带合并

  场景 3 - after_new_publish（鲸芽上新后）
    清空 inventory → 插入鲸芽已发布商品（含新品）→ 写入 jingya_id
    → 只对新商品填充 supplier_map → 回填 → 合并

  场景 4 - reassign_low_stock_preview（预览低库存换供货商建议）
    reassign_low_stock_suppliers(dry_run=True)  ← 不改数据库，仅打印

  场景 5 - reassign_low_stock_apply（确认后执行换供货商）
    reassign_low_stock_suppliers(dry_run=False) → 清空 inventory → 重建

  场景 6 - supplier_overrides（手工 Excel 指定供货商）
    apply_barbour_supplier_overrides(dry_run=False) → 清空 inventory → 重建

================================================================================
  阶段 D：导出库存 & 价格 Excel
  脚本：export_stock_price_to_excel.py
================================================================================

  导出鲸芽库存更新 Excel：
    export_stock_excel("barbour", stock_dest_folder)

  导出鲸芽价格更新 Excel（商品级别）：
    export_jiangya_channel_prices(brand="barbour", output_dir=...)

  （可选）导出各淘宝店铺价格 Excel：
    generate_price_excels_bulk(brand="barbour", input_dir=store_dir, ...)

================================================================================
  阶段 E：图片下载 & 初步处理
  脚本：image_download_and_prepare.py
================================================================================

  1. 从 Barbour 官网下载图片（多线程）：
       download_barbour_images_multi(max_workers=6)

  2. 批量防指纹处理（轻微扰动，防止电商平台查重）：
       batch_process_images(IMAGE_DOWNLOAD, IMAGE_DOWNLOAD)

  3. 按商品编码分组并重命名：
       group_and_rename_images(IMAGE_DOWNLOAD, code_len=11, overwrite=True)

================================================================================
  阶段 F1：选图 & 水印准备
  脚本：image_select_and_prepare.py
================================================================================

  前置：已有发布 Excel（含要发布的商品编码列表）

  1. 按 Excel 编码从下载/处理目录复制图片到 publish_ready 目录
  2. 重建每款商品的图片目录结构
  3. 汇总图片到平铺目录（IMAGE_PROCESS）
  4. 对序号 0-9 的图片添加水印

================================================================================
  阶段 F2（可选）：AI 人物图分类
  脚本：run_classify_person_images.py
================================================================================

  将 need_edit 目录中的图片自动分类：
    - classify/person：含人物（含头部）的模特图
    - classify/detail：细节图、无人物图

  参数：CONFIDENCE=0.4, REQUIRE_HEAD=True, HEAD_CONFIDENCE=0.3

================================================================================
  阶段 G：生成 HTML 详情页 & 图片
  脚本：image_process_and_html.py
================================================================================

  前置：image_select_and_prepare.py 已完成，IMAGE_PROCESS 目录已就绪

  1. 横向合并多张图片为宽图（MERGED_DIR, width=750）
  2. 生成商品详情卡 HTML（含首页 FirstPage）
  3. HTML 渲染为 PNG 图片（多线程，6 线程）
  4. 裁剪图片两侧留白

================================================================================
  阶段 H：生成发布 Excel
  脚本：publish_generate_excel.py
================================================================================

  可选：先导出折扣商品列表（按前缀过滤，如 MWX/LWX）：
    export_barbour_discounts_excel_multi(0, 3, "MWX,MQU,MOL,...")

  主要步骤：
    1. 将要发布的商品编码放到 codes.txt
    2. 执行 generate_publication_excel() → 生成发布 Excel

================================================================================
  工具脚本（按需单独运行，不属于常规流程）
================================================================================

  db_tool_learn_color_map.py
    ─ 从 barbour_products 学习颜色映射，更新 barbour_color_map 表
    ─ 用途：改善颜色归一化准确性

  db_tool_import_keywords_lexicon.py
    ─ 导入标题/描述关键词词库到数据库

  tool_inspect_supplier.py
    ─ 检查各供应商数据质量（价格异常、库存缺失等）

  tool_price_check.py
    ─ 校验 inventory 中价格合规性（是否低于成本价等）

  tool_sizechart_to_image.py
    ─ 将 Barbour 尺码表 HTML 转换为图片，用于详情页插入

================================================================================
  常用场景快速参考
================================================================================

  日常库存更新（供应商数据有变化）：
    A(步骤1+2) → B → C(场景2) → D

  上新发布流程：
    A → B → C(场景3/1) → D → E → F1 → G → H

  只更新价格/库存 Excel（数据库已是最新）：
    D

  新增商品编码匹配（houseoffraser 等无编码来源）：
    B2 → B(步骤4) → C

================================================================================
