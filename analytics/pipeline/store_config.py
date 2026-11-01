from dataclasses import dataclass
from pathlib import Path

# ============================================================
# ⬇  本次要处理的店铺（目录名）：只放一个 = 单店处理；放多个 = 依次处理
#    run_import_data / run_export_data / run_traffic_* 都按这个列表循环
ACTIVE_STORES: list[str] = [
    "fireman",
    "五小剑",
    "英国伦敦代购",
]

# ⬇  导入前是否清空全部旧数据（run_import_data 使用）
#    True  = 导入前先清空 catalog_items + product_metrics_daily 两张表的【所有店铺】数据，
#            库里只留本次导入的数据（注意：ACTIVE_STORES 里没列出的店铺数据也会被清掉）
#    False = 增量导入：只替换本次店铺的商品信息，日报按 (日期, 宝贝ID, 店铺) 覆盖/新增，
#            其它店铺数据和历史日报都保留
RESET_ALL_BEFORE_IMPORT: bool = True
# ============================================================

# 目录名 → 淘宝真实店铺名（= 日报 Excel「店铺名称」列的值）
# 数据库 catalog_items / product_metrics_daily 的 store_name 统一存真实店铺名
# 新增店铺：在此处添加一行，并在 _BASE 下建同名目录
STORE_NAME_MAP: dict[str, str] = {
    "fireman":      "英国维尔顿百货",
    "五小剑":       "英国玛莎百货商店",
    "英国伦敦代购": "英国哈梅尔百货",
}

# 从商品标题推断品牌时使用的关键词（大小写不敏感）
# 新增品牌：在此处添加一行即可
BRAND_KEYWORDS: dict[str, list[str]] = {
    "clarks":   ["clarks", "其乐"],
    "camper":   ["camper", "看步"],
    "ecco":     ["ecco", "爱步"],
    "geox":     ["geox", "健乐士"],
    "barbour":  ["barbour"],
}

_BASE = Path(r"D:\TB\product_analytics\store")



@dataclass(frozen=True)
class Store:
    folder: str        # 目录名，如 "fireman"
    store_name: str    # 淘宝真实店铺名，如 "英国维尔顿百货"

    @property
    def base_dir(self) -> Path:
        return _BASE / self.folder

    @property
    def catalog_dir(self) -> Path:
        return self.base_dir / "input" / "product_info"

    @property
    def metrics_dir(self) -> Path:
        return self.base_dir / "input" / "daily_metrics"

    @property
    def export_dir(self) -> Path:
        return self.base_dir / "export"

    def __str__(self) -> str:
        return f"{self.folder}（{self.store_name}）"


def get_active_stores() -> list[Store]:
    unknown = [f for f in ACTIVE_STORES if f not in STORE_NAME_MAP]
    if unknown:
        raise ValueError(f"ACTIVE_STORES 中有未配置的店铺：{unknown}，请先在 STORE_NAME_MAP 中添加")
    return [Store(f, STORE_NAME_MAP[f]) for f in ACTIVE_STORES]


# 跨店铺对比报告输出目录（不随 ACTIVE_STORES 变化）
CROSS_STORE_EXPORT_DIR = _BASE.parent / "cross_store" / "export"

# ============================================================
# 筛选 sheet 参数（product_export 额外生成的"冷门商品候选"sheet）
# 保留同时满足以下三个条件的商品：
#   1. pay_amount_{days}d <= FILTER_PAY_AMOUNT_MAX（基本无成交）
#   2. visitors_{days}d   <= FILTER_VISITORS_MAX（访问量不高）
#   3. publication_date   早于 FILTER_PUBLICATION_WEEKS 周前（排除新品）
FILTER_PAY_AMOUNT_MAX: float = 0
FILTER_VISITORS_MAX: float = 20
FILTER_PUBLICATION_WEEKS: int = 3

# ============================================================
# 跨店铺差商品规则（run_cross_store_bad_products 使用）
# 单店"差"：同时满足
#   1. 该店最早发布日期距今 >= BAD_MIN_PUBLISH_DAYS 天（排除新品）
#   2. 最近 BAD_WINDOW_DAYS 天（截止到库里最新日报日期）BAD_METRIC 合计 < BAD_METRIC_MAX
#   3. 同期成交件数 <= BAD_MAX_PAY_QTY
# 商品编码在所有上架店铺都"差" → 差商品；
# 差商品若供应商端未打折（库存表 discount_price_gbp 不低于 original_price_gbp）→ 列入删除名单 + 发布黑名单
BAD_WINDOW_DAYS: int = 30
BAD_MIN_PUBLISH_DAYS: int = 10
BAD_METRIC: str = "pageviews"       # 浏览量；可改 "visitors"（访客数）
BAD_METRIC_MAX: int = 10            # 严格小于才算差
BAD_MAX_PAY_QTY: int = 0            # 有成交就不算差；设 None 关闭此条件
# True = 必须在 ACTIVE_STORES 全部店铺都上架（且都差）才算；False = 只要求上架的店铺都差
BAD_REQUIRE_ALL_STORES: bool = True
# 是否把待删除商品写入发布黑名单（cfg/paths.py 的 PUBLISH_BLOCKLIST_FILENAME）
BAD_WRITE_BLOCKLIST: bool = True
# 品牌价格阈值（淘宝一口价 CNY）：只有该店一口价 > 阈值的商品才可能判为差；未列出的品牌不限价格
BAD_MIN_PRICE_BY_BRAND: dict[str, float] = {
    "ecco":    2500,
    "camper":  2500,
    "clarks":  1500,
    "geox":    2000,
    "barbour": 3500,
}

# ============================================================
# 跨店铺优质商品规则（run_cross_store_top_products 使用，选直通车推广候选）
# 统计窗口：最近 TOP_WINDOW_DAYS 天（截止到库里最新日报日期），指标为所有店铺合计
# 综合得分 = Σ 权重 × 该指标在【品牌内】的百分位排名（0~100）
#   按品牌内排名而不是绝对值，避免 Barbour 这种高流量品牌把其它品牌挤掉
# 入选：同时满足下列门槛，再按得分取每个品牌前 TOP_N_PER_BRAND 个
TOP_WINDOW_DAYS: int = 30
TOP_SCORE_WEIGHTS: dict[str, float] = {
    "pageviews":      0.20,   # 浏览量
    "cart_buyer_cnt": 0.35,   # 加购人数
    "pay_qty":        0.45,   # 成交件数
}
TOP_MIN_PAGEVIEWS: int = 50       # 合计浏览量 >= 此值
TOP_MIN_CART: int = 3             # 合计加购人数 >= 此值
TOP_MIN_PAY_QTY: int = 0          # 合计成交件数 >= 此值（0 = 不要求有成交）
TOP_MIN_STORE_CNT: int = 1        # 至少在 N 个店铺上架（2 = 只看多店都上架的商品）
TOP_N_PER_BRAND: int = 30         # 每个品牌最多导出多少个
