"""
手动把商品编码加入发布黑名单。修改下方参数后运行。
已在名单里的编码：重新启用、加入次数 + 1、原因更新。
"""
from pathlib import Path

from common.publication.publish_blocklist import upsert_blocklist

BRAND = "camper"                    # 小写品牌 key（判断打折需要）
CODES: list[str] = [
    # "K100000-001",
]
INPUT_TXT: Path | None = None       # 或者一行一个编码的 TXT（UTF-8），与 CODES 合并
REASON = "手动加入"
RELEASE_ON_DISCOUNT = True          # True = 供应商打折后自动放行；False = 永久拦截

if __name__ == "__main__":
    codes = list(CODES)
    if INPUT_TXT:
        codes += [l.strip() for l in INPUT_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not codes:
        print("⚠️ 没有要加入的编码，请先填写 CODES 或 INPUT_TXT")
    else:
        upsert_blocklist([
            {"product_code": c, "brand": BRAND, "reason": REASON, "source": "manual",
             "release_on_discount": RELEASE_ON_DISCOUNT}
            for c in codes
        ])
