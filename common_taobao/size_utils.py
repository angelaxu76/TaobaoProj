import re

def clean_size_for_barbour(raw_size: str) -> str:
    if not raw_size:
        return None

    raw_size = raw_size.strip().upper()

    ALL_STANDARD_SIZES = set(
        ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "ONESIZE"] +
        [str(s) for s in range(4, 24, 2)] +
        [str(s) for s in range(30, 56, 2)]
    )

    # ✅ 完全命中
    if raw_size in ALL_STANDARD_SIZES:
        return raw_size

    # ✅ 包含某个标准尺码（如 "UK 6" 包含 "6"）
    for std in sorted(ALL_STANDARD_SIZES, key=lambda x: -len(x)):
        if std in raw_size:
            return std

    # ✅ 正则兜底匹配裸数字
    match = re.search(r"\b(\d{1,2})\b", raw_size)
    if match and match.group(1) in ALL_STANDARD_SIZES:
        return match.group(1)

    print(f"❌ 无法识别尺码: {raw_size}")
    return None
