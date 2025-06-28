import shutil
from pathlib import Path
import pandas as pd
from config import BRAND_CONFIG

def copy_product_images_for_recent_publication(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    out_base = Path(config["OUTPUT_DIR"])
    source_image_dir = Path(config["BASE"]) / "document" / "merges"
    target_image_dir = Path(config["BASE"]) / "repulibcation" / "merged"

    # 合并最近发布的两个 Excel 文件（男款和女款）
    files = [
        out_base / f"{brand.lower()}_最近发布_男款商品列表.xlsx",
        out_base / f"{brand.lower()}_最近发布_女款商品列表.xlsx"
    ]
    product_codes = set()
    for file in files:
        if not file.exists():
            print(f"⚠️ 文件未找到: {file}")
            continue
        df = pd.read_excel(file, dtype=str)
        if "商品编码" in df.columns:
            codes = df["商品编码"].dropna().astype(str).str.strip()
            product_codes.update(codes)

    print(f"📦 总共需要复制 {len(product_codes)} 个商品编码对应的图片")

    if not product_codes:
        print("⚠️ 没有商品编码，跳过图片复制")
        return

    # 创建目标目录
    target_image_dir.mkdir(parents=True, exist_ok=True)

    # 扫描并复制图片
    copied_count = 0
    supported_exts = [".jpg", ".jpeg", ".png", ".webp"]
    for file in source_image_dir.glob("*"):
        if file.suffix.lower() not in supported_exts:
            continue
        for code in product_codes:
            if code in file.stem:
                shutil.copy(file, target_image_dir / file.name)
                copied_count += 1
                break

    print(f"✅ 已复制图片数量: {copied_count}（保存至 {target_image_dir}）")
