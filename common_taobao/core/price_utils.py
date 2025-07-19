from decimal import Decimal


def calculate_discount_price(info: dict) -> float:
    """
    根据你之前提供的公式计算价格：
    (价格 × 1.2 + 18) × 1.1 × 1.2 × 9.7
    优先使用 info["AdjustedPrice"]，否则 fallback 到 info["Price"]
    """
    try:
        base_price = float(info.get("AdjustedPrice") or info.get("Price") or 0)
        custom_rate = 1.2
        delivery_cost = 12
        discount_Space = 1.15
        exchange_rate = 9.8
        profit = 1.1

        rmb_price = (base_price * custom_rate + delivery_cost) * profit * discount_Space * exchange_rate
        rounded_price = int(round(rmb_price / 10.0)) * 10

        if base_price < 30:
           rounded_price = rounded_price + 100
        elif 30 < base_price < 50:
           rounded_price = rounded_price+80
        elif 50 < base_price < 80:
           rounded_price = rounded_price+50

        return rounded_price
    except:
        return 0.0


def calculate_discount_price_from_float(base_price: float) -> float:
    try:
        base_price = float(base_price)  # ✅ 强制转换

        custom_rate = 1.2
        delivery_cost = 12
        discount_space = 1.15
        exchange_rate = 9.8

        profit = 1.10



        print(f"🧪 [DEBUG] base_price={base_price}, profit={profit}")

        rmb_price = (base_price * custom_rate + delivery_cost) * profit * discount_space * exchange_rate
        print(f"🧮 [DEBUG] 计算后 rmb_price={rmb_price}")

        rounded_price = int(round(rmb_price / 10.0)) * 10

        if base_price < 30:
           rounded_price = rounded_price + 100
        elif 30 < base_price < 50:
           rounded_price = rounded_price+80
        elif 50 < base_price < 80:
           rounded_price = rounded_price+50

        return rounded_price
    except Exception as e:
        print(f"❌ [price_utils] 错误: base_price={base_price}, 错误: {e}")
        return 0.0


# price_utils.py
from math import floor

from math import floor

def calculate_camper_untaxed_and_retail(original_price, discount_price, delivery_cost=7, exchange_rate=9.7):
    """
    根据原价和折扣价计算不含税价和零售价（人民币）
    original_price: 原价（GBP）
    discount_price: 折扣价（GBP）
    delivery_cost: 固定运费（GBP）
    exchange_rate: 汇率（默认9.7，可动态调整）
    """
    # 确定基础价格
    if original_price > 0 and discount_price > 0:
        base_price = min(original_price, discount_price)
    else:
        base_price = discount_price if discount_price > 0 else original_price

    # 如果价格无效，直接返回 0
    if base_price <= 0:
        return 0, 0

    try:
        # 不含税价计算逻辑
        untaxed = (base_price * 0.75 + delivery_cost) * 1.15 * exchange_rate
        untaxed = floor(untaxed / 10) * 10

        # 零售价计算逻辑
        retail = untaxed * 1.45
        retail = floor(retail / 10) * 10

        return untaxed, retail
    except Exception as e:
        print(f"❌ 价格计算失败: {e}, 输入参数: original={original_price}, discount={discount_price}, exchange_rate={exchange_rate}")
        return 0, 0
