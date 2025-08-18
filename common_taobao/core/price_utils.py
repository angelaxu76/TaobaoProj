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

def calculate_jingya_prices(base_price: float, delivery_cost=7, exchange_rate=9.7):
    """
    接收 base_price（已考虑品牌折扣），返回未税价格与零售价
    """
    from math import floor

    if base_price <= 0:
        return 0, 0

    if base_price < 30:
        base_price = base_price + 7
    elif 30 < base_price < 40:
        base_price = base_price+5

    try:
        untaxed = (base_price + delivery_cost) * 1.13 * exchange_rate
        untaxed = floor(untaxed / 10) * 10

        retail = untaxed * 1.36
        retail = floor(retail / 10) * 10

        return untaxed, retail
    except Exception as e:
        print(f"❌ calculate_jingya_prices 错误: base_price={base_price}, 错误: {e}")
        return 0, 0
