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
     运费）从低到高挑供应商，凑够 SUPPLIER_MIN_SIZES 个有货尺码（或最多
     SUPPLIER_MAX_SITES 家）为止；库存取这几家的并集，定价取这几家里成本最高的
     那个（避免低价供应商断货补货时倒贴运费亏本）。这些阈值 + 淘宝店铺折扣，
     统一在 brands/barbour/jingya/allocate_supplier_and_price_config.py 配置。
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
  图片流水线总览（阶段 E ~ G）
================================================================================

  images/ 下的长期原始素材库是 image_download/（BARBOUR["IMAGE_DOWNLOAD"]，按编码分子目录），
  另有两个阶段E内部中转目录 image_download_raw/ 和 image_download_processed/（扁平散图，
  每次跑阶段E前会被清空重建）。images/ 与 publication / repulibcation 平级，
  backup_and_clear_brand_dirs() 只清空 publication 和 repulibcation，不会碰 images/，
  所以下载库不会被清理流程误删。

  阶段F1~G（选图 ~ HTML产出）的所有批次临时数据统一放在 repulibcation/ 下
  （BARBOUR["IMAGE_SELECTED"] / IMAGE_PERSON_DIR / IMAGE_DETAIL_DIR / IMAGE_PROCESS 等，
  即 PROCESS_BASE），跟 images/ 的原始下载库分开，避免混在一起误删；
  repulibcation/ 会随每批发布被 backup_and_clear_brand_dirs() 备份后清空，
  属于正常的批次产出，不需要长期保留。

  images/
  ├── image_download_raw/        ← 阶段E中转：官网下载的原始散图（扁平，每次跑前清空）
  ├── image_download_processed/  ← 阶段E中转：防指纹处理后的散图（扁平，每次跑前清空）
  └── image_download/            ← 阶段E输出：长期库，按编码分子目录累积所有历史图片

  repulibcation/
  ├── images_selected/         ← 阶段F1输出：本批次要发布的商品图片（按编码分目录）
  ├── missing_codes.txt        ← 阶段F1输出：库里找不到图片的编码
  ├── classify/
  │   ├── person/              ← 阶段F2输出：含人物的模特图 → 交给 AI 换脸脚本处理
  │   └── detail/               ← 阶段F2输出：细节/平铺图，无需换脸
  │                                （与 ops/linkfox/_session_config.py 的 PERSON_DIR 一致）
  ├── linkfox_processed/       ← AI 换脸脚本输出 = 阶段G输入（BARBOUR["IMAGE_PROCESS"]）
  ├── image_merged/            ← 阶段G输出：横向合并宽图
  ├── html/{description,first_page}/
  ├── html_image/{description,first_page}/
  └── html_cutter/{description,first_page}/   ← 阶段G最终产出

================================================================================
  阶段 E：图片下载 & 初步处理
  脚本：image_download_and_prepare.py
================================================================================

  0. 清空两个中转目录 IMAGE_DOWNLOAD_RAW / IMAGE_DOWNLOAD_PROCESSED

  1. 从 Barbour 官网下载图片（多线程）-> IMAGE_DOWNLOAD_RAW：
       download_barbour_images_multi(max_workers=6)
     会先按商品编码检查长期库 IMAGE_DOWNLOAD/<code>/，已下载过的编码直接跳过；
     如需强制重下，传 skip_existing=False（命令行 --force）。

  2. 批量防指纹处理（轻微扰动，防止电商平台查重）RAW -> PROCESSED：
       batch_process_images(IMAGE_IN=IMAGE_DOWNLOAD_RAW, IMAGE_OUT=IMAGE_DOWNLOAD_PROCESSED)

  3. 按商品编码分组并重命名 PROCESSED -> IMAGE_DOWNLOAD（长期库）：
       group_and_rename_images(IMAGE_DOWNLOAD_PROCESSED, code_len=11,
                               overwrite=True, dest_dir=IMAGE_DOWNLOAD)

  说明：防指纹和分组都只认"扁平散图"。RAW / PROCESSED 每次清空重来，
        分组结果只往 IMAGE_DOWNLOAD 累积，重复执行不会因为库里已是编码子目录而错乱。

================================================================================
  阶段 F1：选图
  脚本：image_select_and_prepare.py
================================================================================

  前置：已有发布 Excel（含要发布的商品编码列表）

  按 Excel 编码从 IMAGE_DOWNLOAD（长期库）复制图片到 IMAGE_SELECTED，
  找不到图片的编码写入 IMAGE_MISSING_TXT。

================================================================================
  阶段 F2：AI 人物图分类
  脚本：run_classify_person_images.py
================================================================================

  将 IMAGE_SELECTED 目录中的图片自动分类：
    - classify/person/：含人物（含头部）的模特图 → 交给 AI 换脸脚本（ops/linkfox/）批量处理
    - classify/detail/：细节图、无人物图，无需换脸

  参数：CONFIDENCE=0.4, REQUIRE_HEAD=True, HEAD_CONFIDENCE=0.3

  换脸完成后（ops/linkfox/），输出直接落在 repulibcation/linkfox_processed/，
  即 BARBOUR["IMAGE_PROCESS"]，无需再手动汇总，直接进入阶段G。
  如需混入 detail/ 中的细节图，再手动补充到 linkfox_processed/ 即可。

================================================================================
  阶段 G：生成 HTML 详情页 & 图片
  脚本：image_process_and_html.py
================================================================================

  前置：repulibcation/linkfox_processed/（即 IMAGE_PROCESS）已有换脸图
       （如需细节图一并出图，先手动补充 detail/ 中的图进去）

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
    A → B → C → D → E → F1 → G → H

  只更新价格/库存 Excel（数据库已是最新）：
    D

  新增商品编码匹配（houseoffraser 等无编码来源）：
    B2 → B(步骤4) → C

================================================================================
