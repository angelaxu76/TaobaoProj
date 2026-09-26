# -*- coding: utf-8 -*-
"""
Barbour 日常流水线（prepare_jingya_listing.py）—— 会话级参数唯一入口。

这里集中了跑一次流水线时最可能临时调整的参数：阶段开关、A/B 阶段供应商
列表、C 阶段供应商组合/定价策略、各类导出路径、日志目录。原来这些参数
分散在 prepare_jingya_listing.py 顶部和
brands/barbour/jingya/allocate_supplier_and_price_config.py 两处，现在
统一改这一个文件即可；后者仍保留同名变量，只是转发导入自这里，用来兼容
其他脚本（allocate_supplier_and_price.py / tool_inspect_supplier.py）已有
的 import 路径，不要在那边改值。

不在这里的参数（有明确架构原因，不要往这里搬）：
  - cfg/brands/barbour.py 里的 BARBOUR["SUPPLIER_DISCOUNT_RULES"]
    —— 各供应商在"落地成本价"计算时的折扣策略/运费。它是 cfg/ 层配置，
       而 cfg/ 不能反过来 import brands/ 下的模块（会导致循环 import），
       所以只能留在原地，跟着 import_supplier_to_db_offers.py 一起改。
  - cfg/settings.py 里的 EXCHANGE_RATE、API_KEYS 等全品牌共用的全局设置。
"""

from config import resolve_shared_path

# ══════════════════════════════════════════════════════════════════
#  阶段开关
# ══════════════════════════════════════════════════════════════════
RUN_A_BACKUP    = True   # 备份并清空 TXT 目录（重跑某供货商时设 False）
RUN_A_CRAWL     = True   # A 阶段总开关（False = 跳过整个 A 阶段）
RUN_B_IMPORT    = True   # TXT 导入 products + offers
RUN_C_INVENTORY = True   # 重建 supplier_map + inventory
RUN_D_EXPORT    = True   # 导出库存 / 价格 Excel

# ══════════════════════════════════════════════════════════════════
#  C 阶段：供应商组合策略 / 定价 / 人工干预
#  （原 brands/barbour/jingya/allocate_supplier_and_price_config.py）
# ══════════════════════════════════════════════════════════════════

# 价格窗口：以最低有效成本的供应商为基准，成本不超过
# 基准 × (1 + SUPPLIER_PRICE_TOLERANCE_PCT) 的供应商都一并纳入
# （库存取并集，定价取其中成本最高者）。如果窗口内供应商凑出来的
# 有货尺码数仍然很少，也不会为了凑尺码去找窗口外更贵的供应商——
# 价格窗口内选完就停。
SUPPLIER_PRICE_TOLERANCE_PCT = 0.15
# 无论价格窗口内有多少家满足条件，最多合并几家供应商来覆盖库存
SUPPLIER_MAX_SITES = 3
# 初选供应商时，只有"有货尺码数 >= 此值"的供应商才有资格参与价格窗口
# 排序/入选（包括不能作为最低价基准）。例如某商品 A 供应商报价最低但
# 只有 1 个尺码有货，B 供应商价格略高但 5 个尺码有货：设为 2 时 A 会被
# 排除，改以 B（或更多尺码更全的供应商）为基准，避免"价格最低但几乎
# 断货"的供应商单独垄断分配、导致最终库存只剩一两个尺码。
# 设为 1 = 不做尺码数门槛，等价于旧行为（只要有货就有资格）。
# 若价格窗口容忍比例内没有任何供应商达到这个门槛，会自动回退为不设
# 门槛（避免整个商品被强制清零库存），并在运行日志里打印回退计数。
#
# 2026-09-22 基于全量已发布商品（1145 个）模拟对比 1/2/3 三档的结果：
# 门槛=2 用很小的整体成本代价（均价 +1.6%）几乎修复了所有"能修复"的
# 单尺码断货商品（157 -> 80，77 个被修复）；门槛=3 收益递减（80 -> 85，
# 因"筛空则整体回退不设门槛"是全有全无式的，反而对部分商品产生"回退
# 悬崖"副作用，让本来在门槛=2 下已修复的商品又退回单尺码），且成本
# 接近翻倍。因此选定 2 作为默认值。
SUPPLIER_MIN_SIZES_IN_STOCK = 2

# 未税价 -> 淘宝店铺价的折扣系数（1.0 = 不打折）
TAOBAO_STORE_DISCOUNT = 1.0

# 人工指定供应商（可选）。Excel 需含列：商品编码 / 供货商。命中的商品
# 跳过自动选择，直接用指定站点，但仍走同一套定价/库存回填逻辑。
# 文件不存在时会被自动忽略，不影响正常运行。
SUPPLIER_OVERRIDE_XLSX = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"

# 本次运行临时改一下"最低有货尺码数门槛"（不改上面的 SUPPLIER_MIN_SIZES_IN_STOCK
# 默认值）时，在这里填非 None 的整数；留 None 则使用上面的默认值。
C_MIN_SIZES_IN_STOCK: int | None = None

# ══════════════════════════════════════════════════════════════════
#  均码类别（包 / 帽子 / 围巾等）
# ══════════════════════════════════════════════════════════════════
# 均码类别的编码前缀（product_code 前 3 位），同时用于：
#   1) B 阶段导入：这些前缀的 TXT 若尺码为 "No Data"（页面无尺码选择），
#      按 ONESIZE 入库 barbour_products / barbour_offers；
#      其他前缀遇到 "No Data" 仍跳过（多为鞋服断货/抓取失败，不能当均码有货）。
#   2) 发布候选导出：不受 min_sizes（最少有货尺码数）限制，只要有货即可入选。
ONE_SIZE_PREFIXES = [
    "UBA",  # 中性包袋
    "LBA",  # 女士包袋
    "MHA",  # 男士帽子
    "LHA",  # 女士帽子
    "MHO",  # 兜帽
    "USC",  # 中性围巾
    "LSC",  # 女士围巾
    "MAC",  # 男士配饰（围巾、皮带等）
    "UAC",  # 中性配饰（护理套装、蜡油、徽章、圣诞袜等）
    "MGS",  # 男士礼盒（帽子+围巾/手套、袜子礼盒）
    "LGS",  # 女士礼盒（帽子+围巾等）
    "UFA",  # 鞋类配件（靴袋、护理喷雾；绑腿分尺码，只在 TXT 无尺码时才会当均码）
    "DAC",  # 狗狗用品（玩具、牵引绳、狗窝；项圈/胸背带分尺码，同上）
]

# 发布候选导出沿用同一份名单（兼容旧变量名）
MIN_SIZES_EXEMPT_PREFIXES = ONE_SIZE_PREFIXES

# ══════════════════════════════════════════════════════════════════
#  路径配置
#  共享盘路径统一走 resolve_shared_path()：VM 内用
#  \\vmware-host\Shared Folders\...，本地运行访问不到时自动切到 E:\shared\...
# ══════════════════════════════════════════════════════════════════
EXCLUDE_LIST_XLSX    = resolve_shared_path(r"\\vmware-host\Shared Folders\shared\barbour\barbour_exclude_list.xlsx")
STOCK_EXPORT_DIR     = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\input")
PRICE_EXPORT_DIR     = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\barbour\publication_prices")

# ── D 阶段：淘宝店铺价格导出 ──────────────────────────────────────
# 淘宝店铺导出的 Excel 所在文件夹（每个店铺一个文件）
STORE_PRICE_INPUT_DIR  = resolve_shared_path(r"\\vmware-host\Shared Folders\shared\barbour\store_prices")
# 生成的店铺价格导入表保存位置
STORE_PRICE_OUTPUT_DIR = resolve_shared_path(r"\\vmware-host\Shared Folders\VMShared\barbour\store_prices")

# ── 日志目录（留空则不写文件日志）────────────────────────────────
LOG_DIR = r"D:\TB\Logs\barbour"

# ══════════════════════════════════════════════════════════════════
#  A 阶段：每个供应商独立控制 get_links / fetch_info
#  get_links：True = 重新爬取链接列表；False = 沿用上次已保存的链接
#  fetch_info：True = 抓取商品详情并写 TXT；False = 跳过（保留上次的 TXT）
# ══════════════════════════════════════════════════════════════════
A_SUPPLIERS = {
    #  supplier             get_links  fetch_info
    "barbour":           (  True,      True  ),
    "outdoorandcountry": (  True,     True ),
    "allweathers":       (  True,     True ),
    "terraces":          (  True,     True ),
    "philipmorris":      (  True,     True ),
    "cho":               (  True,     True ),
    "magrigg":           (  True,     True ),
    "williampowell":     (  True,     True ),
    "samturner":         (  True,     True ),
    # "very":            (  False,     False ),
    # houseoffraser 单次运行需 4-6 小时，太耗时，暂时屏蔽
    # "houseoffraser":   (  True,     True ),
}

# ══════════════════════════════════════════════════════════════════
#  B 阶段：要导入的供应商列表
# ══════════════════════════════════════════════════════════════════
B_SUPPLIERS = [
    "barbour",
    "outdoorandcountry",
    "allweathers",
    "terraces",
    "philipmorris",
    "cho",
    "magrigg",
    "williampowell",
    "samturner",
    # "very",
    # houseoffraser 已在 A 阶段屏蔽，不再重复导入
    # "houseoffraser",
]

# B 阶段并发线程数：每个供应商内部会各自新建一条独立数据库连接
# （products 按 product_code+size UPSERT，offers 按 site_name+offer_url+size
#  UPSERT，不同供应商不会写同一行），因此可以安全并行。默认等于供应商数量，
# 超过供应商数量没有意义；如需限制数据库并发连接数可调小。
B_IMPORT_MAX_WORKERS = len(B_SUPPLIERS)
