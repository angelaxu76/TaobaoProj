# test/test_price_calc.py
#
# 用途：输入 GBP 商品价格，查看精雅未税价 / 淘宝零售价
# 运行：python -m test.test_price_calc（从项目根目录）
#
# 修改文件底部 CASES 来测试不同价格

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cfg.price_config import (
    EXCHANGE_RATE,
    DEFAULT_DELIVERY,
    DEFAULT_UNTAXED_MARGIN,
    DEFAULT_RETAIL_MARGIN,
    BRAND_DISCOUNT,
    BRAND_PRICE_OVERRIDES,
    LOW_PRICE_BUMPS,
)
from math import floor


def calc_price(
    gbp: float,
    brand: str = None,
    original_gbp: float = None,
    discount_gbp: float = None,
) -> dict:
    """
    输入 GBP 价格，返回推导过程和最终价格。

    参数：
      gbp          直接指定 base GBP（不走品牌策略，适合快速测试）
      brand        品牌名（用于读取 BRAND_DISCOUNT 和 BRAND_PRICE_OVERRIDES）
      original_gbp 原价（配合 discount_gbp 走完整品牌策略，可选）
      discount_gbp 折扣价（同上，可选）
    """
    brand_key = (brand or "").lower().strip()

    # 1) 品牌折扣率
    ratio = BRAND_DISCOUNT.get(brand_key, 1.0) if brand_key else 1.0
    base = gbp * ratio

    # 2) 品牌级参数覆盖
    overrides = BRAND_PRICE_OVERRIDES.get(brand_key, {})
    delivery       = overrides.get("delivery",       DEFAULT_DELIVERY)
    untaxed_margin = overrides.get("untaxed_margin", DEFAULT_UNTAXED_MARGIN)
    retail_margin  = overrides.get("retail_margin",  DEFAULT_RETAIL_MARGIN)

    # 3) 低价补偿
    bump = 0
    for threshold, b in LOW_PRICE_BUMPS:
        if base < threshold:
            bump = b
            break
    base_bumped = base + bump

    # 4) 公式
    untaxed_raw = (base_bumped + delivery) * untaxed_margin * EXCHANGE_RATE
    untaxed     = floor(untaxed_raw / 10) * 10
    retail_raw  = untaxed * retail_margin
    retail      = floor(retail_raw / 10) * 10

    return {
        "brand":          brand_key or "—",
        "input_gbp":      gbp,
        "ratio":          ratio,
        "base":           base,
        "bump":           bump,
        "base_bumped":    base_bumped,
        "delivery":       delivery,
        "untaxed_margin": untaxed_margin,
        "retail_margin":  retail_margin,
        "exchange_rate":  EXCHANGE_RATE,
        "untaxed":        untaxed,
        "retail":         retail,
    }


def print_price(gbp: float, brand: str = None):
    r = calc_price(gbp, brand=brand)
    brand_label = f"[{r['brand'].upper()}] " if r["brand"] != "—" else ""
    print(f"\n{brand_label}GBP £{r['input_gbp']:.2f}")
    if r["ratio"] != 1.0:
        print(f"  品牌折扣率: ×{r['ratio']}  → base £{r['base']:.2f}")
    if r["bump"]:
        print(f"  低价补偿:   +£{r['bump']}   → £{r['base_bumped']:.2f}")
    print(f"  运费:       +£{r['delivery']}   → £{r['base_bumped'] + r['delivery']:.2f}")
    print(f"  未税加成:   ×{r['untaxed_margin']}  → £{(r['base_bumped'] + r['delivery']) * r['untaxed_margin']:.2f}")
    print(f"  汇率:       ×{r['exchange_rate']}  → ¥{(r['base_bumped'] + r['delivery']) * r['untaxed_margin'] * r['exchange_rate']:.1f}")
    print(f"  ✅ 精雅未税价: ¥{r['untaxed']}")
    print(f"  ✅ 淘宝零售价: ¥{r['retail']}")


def print_table(cases: list[tuple]):
    """
    快速打印多个价格的对比表。
    cases: [(gbp, brand), ...]  brand 可以是 None
    """
    print(f"\n{'品牌':<10} {'GBP':>8} {'鲸芽未税':>10} {'淘宝零售':>10}")
    print("-" * 42)
    for gbp, brand in cases:
        r = calc_price(gbp, brand=brand)
        print(f"{r['brand']:<10} £{gbp:>6.2f}   ¥{r['untaxed']:>7}   ¥{r['retail']:>7}")


# ─────────────────────────────────────────────────────────────────────────────
# 修改这里来测试
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # 详细推导（适合查看单个商品）
    print_price(145,  brand="camper")
    print_price(100, brand="camper")
    print_price(38,  brand="clarks")
    # print_price(25,  brand="geox")

    # 对比表（适合批量检查价格合理性）
    print()
    CASES = [
        (50,  "camper"),
        (80,  "camper"),
        (100, "camper"),
        (150, "camper"),
        (60,  "ecco"),
        (90,  "ecco"),
        (50,  "geox"),
        (80,  "clarks"),
        (200, "barbour"),
    ]
    print_table(CASES)
