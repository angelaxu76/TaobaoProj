def calculate_discount_price(info: dict) -> float:
    """
    根据你之前提供的公式计算价格：
    (价格 × 1.2 + 18) × 1.1 × 1.2 × 9.7
    优先使用 info["AdjustedPrice"]，否则 fallback 到 info["Price"]
    """
    try:
        base_price = float(info.get("AdjustedPrice") or info.get("Price") or 0)
        rmb_price = (base_price * 1.2 + 18) * 1.1 * 1.2 * 9.7
        return round(rmb_price, 2)
    except:
        return 0.0
