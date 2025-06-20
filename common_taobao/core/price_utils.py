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

        if base_price > 50:
            profit = 1.07
        else:
            profit = 1.25

        rmb_price = (base_price * custom_rate + delivery_cost) * profit * discount_Space * exchange_rate
        rounded_price = int(round(rmb_price / 10.0)) * 10
        return rounded_price
    except:
        return 0.0
