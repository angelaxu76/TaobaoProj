import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 添加项目根目录到 sys.path（假设当前文件在 brands/clarks/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from config import BRAND_CONFIG
from brands.clarks.core.GetProductURLs import get_regular_product_links
from brands.clarks.core.GetOutletProductURL import get_outlet_product_links


def generate_product_links(brand: str):
    cfg = BRAND_CONFIG.get(brand.lower())
    if not cfg:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    output_file = cfg["BASE"] / "publication" / "product_links.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    regular_links = get_regular_product_links()
    outlet_links = get_outlet_product_links()

    all_links = sorted(set(regular_links + outlet_links))

    with open(output_file, "w", encoding="utf-8") as f:
        for link in all_links:
            f.write(link.strip() + "\n")

    print(f"✅ [{brand}] 共写入链接 {len(all_links)} 条到: {output_file}")


if __name__ == "__main__":
    generate_product_links("clarks")
