import os
import subprocess
from config import REISS
from brands.reiss.core.reiss_link_collector import reiss_get_links
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs


def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(REISS)

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    DEFAULT_CATEGORIES = REISS.get("CATEGORY_BASE_URLS", [])
    cats = DEFAULT_CATEGORIES or [
        "https://www.reiss.com/shop/feat-sale-gender-women-0",
        "https://www.reiss.com/shop/feat-sale-gender-men-0",
    ]
    reiss_get_links(cats, headless=True)


if __name__ == "__main__":
    main()
