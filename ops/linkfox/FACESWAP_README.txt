================================================================================
  Barbour 女款模特换脸流程说明
  脚本位置：ops/linkfox/
================================================================================

前提条件
--------
  - 已从 Barbour 官网下载好商品图片（文件名格式：{code}_1.jpg, {code}_2.jpg ...）
  - 图片放在某个本地目录（模特图、细节图、平铺图混合）
  - 已准备好目标女模特头部参考图的 URL（用于换脸）
  - rclone 已配置好 Cloudflare R2 的 remote（用于上传图片）

================================================================================
  Step 1：分类图片（人物图 vs 细节/平铺图）
  脚本：brands/barbour/pipeline/run_classify_person_images.py
================================================================================

  修改参数：
    INPUT_DIR  = r"D:\TB\Products\barbour\images_download"   ← 你的下载图片目录
    PERSON_DIR = r"D:\TB\Products\barbour\classify\person"   ← 人物图输出目录
    DETAIL_DIR = r"D:\TB\Products\barbour\classify\detail"   ← 细节/平铺图输出目录
    REQUIRE_HEAD = True   ← True = 必须有头部才算人物图（过滤手/腿细节图）

  运行：
    python brands/barbour/pipeline/run_classify_person_images.py

  运行后：
    - classify/person/  → 所有含人物头部的模特图
    - classify/detail/  → 细节图 + 平铺图

  ⚠️ 人工检查：
    快速翻看 classify/person/ 目录，将男款模特图手动移走，
    只保留女款模特图。
    （Barbour 女款编码以 L 开头，男款以 M 开头，可据此快速判断）

================================================================================
  Step 2：给文件名加入镜头关键字
  脚本：ops/run_rename_images.py
================================================================================

  目的：将 MWX2343BL56_1.jpg → MWX2343BL56_front_1.jpg
        使文件名与后续 R2 URL 命名规则一致

  修改参数：
    INPUT_DIR  = r"D:\TB\Products\barbour\classify\person"   ← Step 1 输出的人物图目录
    OUTPUT_DIR = INPUT_DIR                                    ← 就地重命名（同一目录）
    KEYWORD    = "front"                                      ← 镜头类型标识
    DRY_RUN    = True                                         ← 先设 True 预览

  先预览运行（DRY_RUN = True）：
    python ops/run_rename_images.py
    → 确认控制台输出的重命名预览正确

  确认无误后改为实际执行（DRY_RUN = False）：
    python ops/run_rename_images.py
    → 文件就地重命名完成

================================================================================
  Step 3：上传图片到 Cloudflare R2
  工具：rclone（命令行）
================================================================================

  将 Step 2 处理好的女款模特图批量上传到 R2：

    rclone copy "D:\TB\Products\barbour\classify\person" ^
           r2:你的bucket名/product_front ^
           --include "*.jpg" --progress

  上传后验证（浏览器打开以下 URL 应能看到图片）：
    https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/product_front/MWX2343BL56_front_1.jpg

  ⚠️ 若 URL 返回 404，检查：
    1. bucket 名称是否正确
    2. 子目录名（product_front）是否与上传路径一致
    3. 文件名后缀是否已在 Step 2 中添加 front 关键字

================================================================================
  Step 4：配置本次任务参数
  脚本：ops/linkfox/_session_config.py
================================================================================

  修改以下参数（其他保持不动）：

    # 品牌根目录
    BRAND_ROOT = Path(r"D:\TB\Products\barbour")

    # Step 3 上传到 R2 的子目录名
    R2_SHOT_SUBDIR = "product_front"

    # 每款处理的原图后缀（与 Step 2 的 KEYWORD 对应）
    # 只处理每款第一张：
    SHOT_SUFFIXES = ["_front_1"]
    # 若要处理每款两张：
    # SHOT_SUFFIXES = ["_front_1", "_front_2"]

    # 目标模特头部参考图（填入你准备好的目标女模特图 URL）
    TARGET_MODEL_URLS = [
        "https://你的目标模特图URL.jpg",
        # 多个模特轮流分配：继续添加更多 URL
        # "https://第二个模特图URL.jpg",
    ]

================================================================================
  Step 5：准备商品编码 Excel
  文件：D:\TB\Products\barbour\codes.xlsx
================================================================================

  在 codes.xlsx 的第一列填入需要换脸的女款商品编码：

    第一行：商品编码（表头，对应脚本中 HEADER_ROWS = 1）
    第二行起：每行一个编码，例如：
      MWX2343BL56
      LWX1234NY99
      LCA0123BK11
      ...

  注意：
    - 只填女款编码（以 L 开头为主）
    - 编码对应的图片必须已在 Step 3 上传到 R2
    - 文件路径必须与 _session_config.py 中 CODES_EXCEL 一致
      即：BRAND_ROOT / "codes.xlsx" = D:\TB\Products\barbour\codes.xlsx

================================================================================
  Step 6：运行换脸脚本
  脚本：ops/linkfox/run_linkfox_faceswap.py
================================================================================

  确认脚本顶部参数（一般无需修改）：
    HEADER_ROWS  = 1      ← Excel 有表头行
    OUTPUT_NUM   = 1      ← 每张原图生成 1 张换脸结果
    MAX_WORKERS  = 3      ← 并发线程数（建议 2~3，避免 API 限流）
    REAL_MODEL   = True   ← 真人模特

  运行：
    python ops/linkfox/run_linkfox_faceswap.py

  输出：
    文件保存在 D:\TB\Products\barbour\linkfox_output\
    命名格式：{code}_front_1_faceswap.jpg
    例：MWX2343BL56_front_1_faceswap.jpg

  若有失败的编码：
    - 失败列表会自动保存到 linkfox_output/failed_codes_{时间戳}.txt
    - 修复问题后可将失败编码放入新的 codes.xlsx，重新运行

================================================================================
  Step 7：换脸图后处理（抠图 + 白底正方形 + 水印）
  脚本：ops/linkfox/run_cut_square_watermark.py
================================================================================

  在 Step 6 换脸完成后运行，将换脸图处理为淘宝主图规格：
    - 自动抠图（rembg birefnet-general），去除场景/背景
    - 按 alpha 精裁 → 正方形白底居中
    - 斜纹水印 + 右下角小字水印
    - 输出 JPG，统一 1500×1500 px

  输入/输出目录由 _session_config.py 自动推导，一般无需修改：
    INPUT_DIR  = LINKFOX_DIR          即 BRAND_ROOT/linkfox_output/
    OUTPUT_DIR = BRAND_ROOT/linkfox_processed/

  可按需调整的参数：
    AUTO_CUTOUT   = True    ← True=抠图去背景；False=只裁方+水印（极快）
    WHITE_BG_SKIP = True    ← 检测到白底图跳过抠图，节省时间
    MAX_WORKERS   = 4       ← 抠图时建议 ≤ 4（CPU 密集）
    TARGET_SIZE   = 1500    ← 输出边长 px

  运行：
    python ops/linkfox/run_cut_square_watermark.py

  输出：
    文件保存在 BRAND_ROOT/linkfox_processed/
    例：MWX2343BL56_front_1_faceswap.jpg

  水印文字、字体、颜色等细节参数在以下文件中修改：
    helper/image/cut_square_white_watermark.py

================================================================================
  快速检查清单
================================================================================

  Step 1 ✓  classify/person/ 目录已只剩女款模特图
  Step 2 ✓  文件名已变为 {code}_front_{n}.jpg 格式
  Step 3 ✓  浏览器能打开 R2 URL 看到图片（做一张抽查即可）
  Step 4 ✓  _session_config.py 中 SHOT_SUFFIXES / TARGET_MODEL_URLS 已填写
  Step 5 ✓  codes.xlsx 第一列是编码，路径在 BRAND_ROOT 下
  Step 6 ✓  运行后 linkfox_output/ 目录有生成图片
  Step 7 ✓  运行后 linkfox_processed/ 目录有白底正方形水印图

================================================================================
  常用后续操作
================================================================================

  查看换脸质量对比：
    python ops/linkfox/run_compare_faceswap_quality.py

  找出未处理的编码（R2 有原图但没有换脸结果）：
    python ops/linkfox/run_find_unprocessed_faceswap.py

  对失败的编码自动重试：
    python ops/linkfox/run_faceswap_retry_loop.py

================================================================================
