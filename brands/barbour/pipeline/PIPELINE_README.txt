================================================================================
  Barbour Pipeline 脚本执行顺序说明
  文件位置：brands/barbour/pipeline/
================================================================================

【总体流程概览】

  A. 抓取供应商数据  →  B. 导入数据库  →  C. 构建库存  →  D. 导出库存/价格 Excel
  E. 图片下载处理   →  F. 选图/水印/分类  →  G. HTML 详情图  →  H. 生成发布 Excel

================================================================================
  阶段 A：抓取供应商商品信息
  脚本：prepare_jingya_listing.py（RUN_A_CRAWL=True 时执行，见文件顶部 A_SUPPLIERS）
================================================================================

  注：旧的独立脚本 crawl_supplier_info.py 已移到 brands/barbour/legacy/ ——
  它抓的供应商列表早就跟不上了（少了 magrigg/williampowell/samturner，houseoffraser
  也没像现在这样因为太慢而停用），不要再当作阶段 A 的入口用。

  步骤 0（可选，RUN_A_BACKUP）：清空 TXT + 发布目录（备份旧数据）
    backup_and_clear_brand_dirs(BARBOUR)

  步骤 1+2：按 A_SUPPLIERS 逐个站点获取链接 + 抓取商品详情 → 写入 TXT 文件
    barbour / outdoorandcountry / allweathers / terraces / philipmorris /
    cho / magrigg / williampowell / samturner
    （very 停用；houseoffraser 单次运行需 4-6 小时，太耗时，也停用，
     保留 import 供随时恢复）

  步骤 3：移除 TXT 目录中无 Barbour 编码的文件（cho/philipmorris/terraces/
          magrigg/williampowell/samturner）

================================================================================
  阶段 B：将 TXT 导入数据库
  脚本：prepare_jingya_listing.py（RUN_B_IMPORT=True 时执行，见文件顶部 B_SUPPLIERS）
================================================================================

  注：旧的独立脚本 db_import_txt_products_offers.py 已移到 brands/barbour/legacy/ ——
  同样缺了 magrigg/williampowell/samturner，不要再当作阶段 B 的入口用。

  按 B_SUPPLIERS 逐个供应商：
    batch_import_txt_to_barbour_product(supplier)   → barbour_products
    import_txt_for_supplier(supplier, clear_first=True)  → barbour_offers
      （clear_first=True：先清空该供应商旧数据再从 TXT 重建，避免残留）

    supplier 列表：barbour / outdoorandcountry / allweathers / terraces /
    philipmorris / cho / magrigg / williampowell / samturner

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
  阶段 C：构建 Inventory + 供应商/价格/库存分配
  脚本：allocate_supplier_and_price.py（单一入口，替代旧的 db_build_supplier_map_and_inventory.py）
================================================================================

  1. 清空 inventory → 插入鲸芽已发布商品（含新品，stock=0 占位）→ 写入 jingya_id
       clear_barbour_inventory() / insert_missing_products_with_zero_stock() / insert_jingyaid_to_db()

  2. 供应商组合 + 价格 + 库存一次性同步：
       allocate_and_sync(brand="barbour", exclude_xlsx=..., dry_run=False)

     每个已发布商品：按"真实落地成本"（barbour_offers.sale_price_gbp，已含折扣策略+
     运费）找出成本最低的供应商作为基准，凡是成本不超过"基准 ×
     (1 + SUPPLIER_PRICE_TOLERANCE_PCT)"的供应商都一并纳入（最多凑满
     SUPPLIER_MAX_SITES 家）；库存取这几家的并集，定价取这几家里成本最高的
     那个（避免低价供应商断货补货时倒贴运费亏本）。价格窗口内供应商凑不够
     尺码时不会去找窗口外更贵的供应商。这些阈值 + 淘宝店铺折扣，统一在
     brands/barbour/jingya/allocate_supplier_and_price_config.py 配置。
     每次运行都会重新计算，不再需要单独的"低库存换供应商"场景。

     可选人工干预（均为参数，不再是独立场景）：
       - exclude_xlsx（barbour_exclude_list.xlsx）：跳过自动分配；若同一份 Excel
         含 source_price_gbp/discount_price_gbp 列，会在最后覆盖为人工固定价。
       - supplier_override_xlsx（barbour_supplier.xlsx）：强制指定供应商，仍走同一套
         定价/库存回填逻辑。

     预览：allocate_and_sync(..., dry_run=True) 只打印将发生的变更，不写库。
     诊断单个商品：tool_inspect_supplier.py <product_code>（会展示当前分配 +
     自动算法会选出的组合预览）。

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
  图片流水线（阶段 E ~ G）
  目录：brands/barbour/pipeline/image/   详细说明见该目录 README.md
================================================================================

  参数只改 image/image_session.py；不知道跑到哪一步时运行 image/status.py。

    step1_prepare.py        下载 → 防指纹 → 入长期库 → 选图 → 人物/细节分类
      ✋ 剔除 classify/person 里不适合换脸的图
    step2_faceswap.py       加 _front_ 关键字 → 上传 R2 → 换脸 → 质量对比 → 自动重试
                            （FACESWAP_BATCH = "men" / "women" 各跑一次）
      ✋ 检查换脸效果
    step3_cutout_split.py   细节图按抠图难易拆分
      ✋ 复核 detail / detail_difficult
    step4_finalize_html.py  抠图 → 汇总 → 按优先级改名 __N → HTML → 渲染 → 裁边

  旧的单步脚本（image_download_and_prepare / image_select_and_prepare /
  run_classify_person_images / run_rename_faceswap_images / image_process_and_html）
  已移到 brands/barbour/legacy/，逻辑已并入上面的 step 脚本。

  images/image_download/ 是长期原始素材库，backup_and_clear_brand_dirs() 不会清理；
  其余批次数据都在 repulibcation/ 下，随每批发布备份后清空。

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

  tool_export_price_stock_report.py
    ─ 导出人可读报表：每个已发布商品当前的供货商组合/定价依据供货商/
      折扣率/售价/库存，纯查询不写库；核心逻辑在
      allocate_supplier_and_price.py 的 export_price_stock_supplier_report()

================================================================================
  常用场景快速参考
================================================================================

  日常库存更新（供应商数据有变化）：
    A(步骤1+2) → B → C → D

  上新发布流程：
    A → B → C → D → 图片流水线 step1~4 → H

  只更新价格/库存 Excel（数据库已是最新）：
    D

  新增商品编码匹配（houseoffraser 等无编码来源）：
    B2 → B(步骤4) → C

================================================================================
