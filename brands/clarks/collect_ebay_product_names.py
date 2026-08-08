import re
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding='utf-8')

# 添加项目根目录到 sys.path（假设当前文件在 brands/clarks/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from config import BRAND_CONFIG

# _sop=15（按上架时间排序）用于固定排序顺序：eBay 默认的 Best Match 排序会掺杂个性化/推荐内容，
# 导致同一页码在不同请求间返回的商品不一致，翻页会漏掉商品。
STORE_URL_TEMPLATE = "https://www.ebay.co.uk/str/clarksukofficial?_ipg=72&_pgn={page}&_tab=shop&_sop=15"
ITEM_NAME_PATTERN = re.compile(r'aria-label="([^"]+)"[^>]*class=str-item-card__link')
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

MAX_PAGES = 40
MAX_EMPTY_NEW_STREAK = 2  # 连续N页无新增商品名即停止翻页（eBay 翻页超过实际库存后会开始循环推荐相似商品）
DELAY_PER_REQUEST = 1


def get_names_from_page(page: int) -> list[str]:
    url = STORE_URL_TEMPLATE.format(page=page)
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {url}，错误: {e}")
        return []

    return ITEM_NAME_PATTERN.findall(response.text)


def get_ebay_product_names() -> list[str]:
    seen = set()
    ordered_names = []
    empty_new_streak = 0

    for page in range(1, MAX_PAGES + 1):
        names = get_names_from_page(page)
        if not names:
            print(f"  🔹 第 {page} 页: 无商品，停止翻页")
            break

        new_count = 0
        for name in names:
            if name not in seen:
                seen.add(name)
                ordered_names.append(name)
                new_count += 1

        print(f"  🔹 第 {page} 页: 获取 {len(names)} 条，新增 {new_count} 条")

        if new_count == 0:
            empty_new_streak += 1
            if empty_new_streak >= MAX_EMPTY_NEW_STREAK:
                print(f"  ⏹ 连续 {MAX_EMPTY_NEW_STREAK} 页无新增商品，停止翻页")
                break
        else:
            empty_new_streak = 0

        time.sleep(DELAY_PER_REQUEST)

    return ordered_names


def generate_ebay_product_names(brand: str = "clarks"):
    cfg = BRAND_CONFIG.get(brand.lower())
    if not cfg:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    output_file = cfg["BASE"] / "publication" / "ebay_product_names.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    names = get_ebay_product_names()

    with open(output_file, "w", encoding="utf-8") as f:
        for name in names:
            f.write(name.strip() + "\n")

    print(f"✅ [{brand}] 共写入 eBay 商品名称 {len(names)} 条到: {output_file}")


if __name__ == "__main__":
    generate_ebay_product_names("clarks")
