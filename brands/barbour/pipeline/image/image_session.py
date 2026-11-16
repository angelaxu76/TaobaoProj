# -*- coding: utf-8 -*-
"""
Barbour 图片流水线 —— 本批次参数唯一入口。

step1 ~ step4 的所有可调参数都在这里；跑之前只需要看这一个文件。
目录路径全部从 cfg/brands/barbour.py 的 BARBOUR 推导，一般不用改。

注意：step2 直接把这里的参数注入 ops/linkfox/run_linkfox_faceswap_direct.py，
不读 ops/linkfox/_session_config.py 里的 BRAND_ROOT / TARGET_MODEL_URLS /
SHOT_SUFFIXES，所以那边切到别的品牌也不影响 Barbour（API Key 仍从那边读）。
"""
from cfg.brands.barbour import BARBOUR

# ══════════════════════════════════════════════════════════════════
#  目录（从 BARBOUR 推导，一般不改）
# ══════════════════════════════════════════════════════════════════
REPUB            = BARBOUR["OUTPUT_DIR"]                     # repulibcation/
CODES_EXCEL      = REPUB / "codes.xlsx"                      # 本批次总编码表（选图 / HTML 用，step2 不会改写它）
IMAGE_SELECTED   = BARBOUR["IMAGE_SELECTED"]                 # step1 选图输出
PERSON_DIR       = BARBOUR["IMAGE_PERSON_DIR"]               # classify/person
DETAIL_DIR       = BARBOUR["IMAGE_DETAIL_DIR"]               # classify/detail（step3 后 = 适合抠图）
DETAIL_HARD_DIR  = REPUB / "classify" / "detail_difficult"   # step3 输出：不适合抠图
FLAT_DIR         = REPUB / "classify" / "平铺"               # step3 后人工从 detail 挑出的平铺图（step4 抠图来源之一）
LINKFOX_DIR      = REPUB / "linkfox_output"                  # 换脸原始输出
LINKFOX_BAD      = REPUB / "linkfox_bad"                     # 质量对比剔除的换脸图
COMPARE_CSV      = REPUB / "linkfox_compare_report.csv"
IMAGE_PROCESS    = BARBOUR["IMAGE_PROCESS"]                  # linkfox_processed：step4 汇总后的最终图源

# ══════════════════════════════════════════════════════════════════
#  step1：下载 / 选图 / 人物分类
# ══════════════════════════════════════════════════════════════════
RUN_DOWNLOAD     = False    # 从官网下载 + 防指纹 + 按编码入长期库
FORCE_REDOWNLOAD = False   # True = 长期库里已有的编码也重新下载
RUN_SELECT       = True    # 按 codes.xlsx 从长期库选图
RUN_CLASSIFY     = True    # 人物 / 细节分类

CLASSIFY_CONFIDENCE      = 0.4
CLASSIFY_REQUIRE_HEAD    = True   # True = 检测到头部才算人物图
CLASSIFY_HEAD_CONFIDENCE = 0.3

# ══════════════════════════════════════════════════════════════════
#  step2：换脸（男 / 女分两批跑：改 FACESWAP_BATCH 后各跑一次 step2）
# ══════════════════════════════════════════════════════════════════
FACESWAP_BATCH = "women"     # 本次跑哪一批，对应下面 FACESWAP_BATCHES 的 key

# 每批：
#   model_urls    —— 目标模特头部参考图，多个时按商品顺序轮流分配
#   code_prefixes —— 按编码前缀筛选本批商品（Barbour 男款 M、女款 L）；
#                    设为 None 表示 classify/person 里的全部编码
#   codes_file    —— 可选：直接指定本批编码 Excel（第一列，带表头），
#                    设置后忽略 code_prefixes
FACESWAP_BATCHES = {
    "men": {
        "code_prefixes": ("M",),
        "codes_file": None,
        "model_urls": [
            "https://file-ai.linkfox.com/UPLOAD/MANAGE/3e5b7430dd824ac79b9d398fc6ad699b.jpg?x-oss-process=image/resize,m_mfit,w_512,h_512&dv2=646174613a732832323a3138373130373539393838303935383737313229",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_1.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_2.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_4.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_5.jpeg",
        ],
    },
    "women": {
        "code_prefixes": ("L",),
        "codes_file": None,
        "model_urls": [
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_2.png",
            # "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_3.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_4.png",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_7.jpeg",
            "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_8.jpeg",
            # "https://file-ai.linkfox.com/UPLOAD/MANAGE/8f941970caa04ccc8fde3eca9a9fe2cc.jpg?x-oss-process=image/resize,m_mfit,w_512,h_512&dv2=646174613a732832323a3138373130383439343336353336303132383029",
        ],
    },
}

SHOT_KEYWORD   = "front"                              # classify/person 里的图改名为 {code}_front_{n}
SHOT_SUFFIXES  = ["_front_1", "_front_2", "_front_3"]  # 每款换哪几张
R2_SHOT_SUBDIR = "product_front"                      # R2 上的子目录

RUN_UPLOAD = True   # 上传本批待换脸的原图到 R2（已上传过可设 False 省时间）

# 换脸 → 质量对比（衣服被改的图移到 linkfox_bad）→ 统计未完成 → 重试。
# 每轮都按 "待处理款数 × 张数 × 20 点" 扣费；某一轮没有任何进展时自动停止。
FACESWAP_MAX_ROUNDS = 3

# ══════════════════════════════════════════════════════════════════
#  step3：细节图按抠图难易拆分
# ══════════════════════════════════════════════════════════════════
CUTOUT_HARD_THRESHOLD = 0.65   # 前景占比 >= 阈值判为难抠图，越高越严格

# ══════════════════════════════════════════════════════════════════
#  step4：抠图 + 汇总 + 改名 + HTML
# ══════════════════════════════════════════════════════════════════
# 子步骤开关（按执行顺序）：只想跑其中几步时，把其余的设为 False。
# 跑 step4 之前：step3 拆好 detail / detail_difficult → 人工把平铺图从 detail 挑到 classify/平铺。
# 改名(RUN_RENAME)之后 linkfox_processed 变成 {code}__N，此时 2~5 会拒绝执行，
# 要重做抠图须先清空 linkfox_processed。
RUN_TAG_DETAILS  = False  # 1. （不挑平铺图时用）detail / detail_difficult 里每款编号最小的一张
                          #    自动改名为 {code}_details；挑了平铺图就保持 False，交给第 4 步
RUN_CUT_FACESWAP = True   # 2. 换脸图 linkfox_output → 抠图白底正方形 → linkfox_processed
RUN_CUT_DETAIL   = True   # 3. 适合抠图的 classify/detail → 抠图白底正方形 → linkfox_processed
RUN_CUT_FLAT     = True   # 4. 平铺图 classify/平铺 → 抠图白底正方形 → linkfox_processed，
                          #    再把每款编号最小的一张输出图改名为 {code}_details，
                          #    按 IMAGE_RENAME_PRIORITY 排到第 2 位（平铺目录里的原图不改名）
RUN_COPY_HARD    = True   # 5. 不适合抠图的 classify/detail_difficult → 原样复制到 linkfox_processed
RUN_RENAME       = True   # 6. 按 image_priority_config 改名为 {code}__1/__2/...（HTML 选图依赖）
RUN_MERGE        = True   # 7. 合并宽图 → image_merged
RUN_GEN_HTML     = True   # 8. 生成详情页 / 首页 HTML
RUN_RENDER       = True   # 9. HTML 渲染为图片 + 裁边 → html_cutter

CUT_AUTO_CUTOUT   = True       # False = 只裁正方形不抠图
CUT_WHITE_BG_SKIP = False      # True = 检测到白底就跳过抠图
CUT_ADD_WATERMARK = False
CUT_TARGET_SIZE   = 1500
CUT_MAX_WORKERS   = 2          # rembg 推理吃 CPU，建议 <= 4
CUT_FUR_CODES: set[str] = set()       # 毛绒商品走专用去毛边，如 {"LHA0555CR11"}
CUT_FUR_PREFIXES: tuple[str, ...] = ("LHA",)

HTML_MAX_WORKERS   = 2
RENDER_MAX_WORKERS = 6
