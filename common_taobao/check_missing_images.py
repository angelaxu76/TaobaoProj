import os
from pathlib import Path
from config import BRAND_CONFIG

def get_all_product_codes(txt_dir: Path) -> set:
    """从 TXT 文件名中提取所有商品编码（不带扩展名）"""
    return {
        f.stem for f in txt_dir.glob("*.txt")
        if f.is_file()
    }

def has_images(product_code: str, image_dir: Path) -> bool:
    """判断该商品编码是否至少有一张图片"""
    return any(image_dir.glob(f"{product_code}*.jpg"))

def check_missing_images(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 不支持的品牌：{brand}")
        return

    config = BRAND_CONFIG[brand]
    txt_dir = config["TXT_DIR"]
    image_dir = config["IMAGE_DIR"]
    output_file = config["BASE"] / "repulibcation" / "missing_images.txt"

    # 1. 获取所有商品编码
    product_codes = get_all_product_codes(txt_dir)
    print(f"📦 共读取商品编码 {len(product_codes)} 个")

    # 2. 查找缺图商品
    missing = []
    for code in sorted(product_codes):
        if not has_images(code, image_dir):
            missing.append(code)

    # 3. 写入结果
    with open(output_file, "w", encoding="utf-8") as f:
        for code in missing:
            f.write(code + "\n")

    print(f"✅ 缺图商品 {len(missing)} 个，结果已保存：{output_file}")

if __name__ == "__main__":
    # 替换为你要检查的品牌名，如 'clarks', 'camper', 'geox'
    check_missing_images("clarks")
