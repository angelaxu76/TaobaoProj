import re

# 别名映射：统一成标准写法
ALIASES = {
    # 大码
    "1XL": "XL",
    "2XL": "XXL",
    "3XL": "XXXL",
    "4XL": "XXXXL",
    "5XL": "XXXXXL",
    "6XL": "XXXXXXL",

    # 小码
    "XS": "XS",
    "2XS": "XXS",
    "XXS": "XXS",
    "3XS": "XXXS",
    "XXXS": "XXXS",

    # 常见英文别写
    "XSMALL": "XS",
    "X-SMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "X-LARGE": "XL",
    "XLARGE": "XL",
    "X LARGE": "XL",

    # 均码
    "ONE SIZE": "ONESIZE",
    "ONESIZE": "ONESIZE",
    "O/S": "ONESIZE",
}

def clean_size_for_barbour(raw_size: str) -> str | None:
    if not raw_size:
        return None

    # 统一大小写和空格
    raw = raw_size.strip().upper().replace(" ", "").replace("-", "")

    # 标准集合
    ALL_STANDARD_SIZES = set(
        [
            "XXXS", "XXS", "XS", "S", "M", "L", "XL",
            "XXL", "XXXL", "XXXXL", "XXXXXL", "XXXXXXL",
            "ONESIZE"
        ]
        + [str(s) for s in range(4, 24, 2)]   # 女装 UK 号 4–22
        + [str(s) for s in range(30, 56, 2)]  # 男裤腰围 30–54
    )

    # ✅ 别名优先映射
    if raw in ALIASES:
        return ALIASES[raw]

    # ✅ 完全命中
    if raw in ALL_STANDARD_SIZES:
        return raw

    # ✅ 包含某个标准尺码（如 "UK6" 包含 "6"）
    for std in sorted(ALL_STANDARD_SIZES, key=lambda x: -len(x)):
        if std in raw:
            return std

    # ✅ 数字兜底
    match = re.search(r"\b(\d{1,2})\b", raw)
    if match and match.group(1) in ALL_STANDARD_SIZES:
        return match.group(1)

    print(f"❌ 无法识别尺码: {raw_size}")
    return None
