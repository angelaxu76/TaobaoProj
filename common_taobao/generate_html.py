import sys
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from common_taobao.core.translate import safe_translate
from common_taobao.core.ad_sanitizer import sanitize_text, sanitize_features
from config import BRAND_CONFIG

PLACEHOLDER_IMG = "https://via.placeholder.com/500x500?text=No+Image"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{product_name}</title>
<style>
    body {{
        font-family: "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
        background: #F5F5F5;
        margin: 0;
        padding: 40px;
        display: flex;
        justify-content: center;
        color: #2B2B2B;
    }}
    .card {{
        width: 800px;
        background: #fff;
        border-radius: 12px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.08);
        padding: 32px 36px;
    }}
    .card h1 {{
        font-size: 28px;
        font-weight: 700;
        color: #2B2B2B;
        margin-bottom: 18px;
        text-align: left;
        border-bottom: 0.5pt dashed #ccc;
        padding-bottom: 10px;
    }}
    .top-section {{
        display: flex;
        gap: 24px;
        margin-bottom: 28px;
    }}
    .product-img {{
        flex: 1;
        background: #fafafa;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        padding: 12px;
        display: flex;
        justify-content: center;
        align-items: center;
    }}
    .product-img img {{
        max-width: 100%;
        border-radius: 8px;
    }}
    .features {{
        flex: 1;
        background: #fff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 14px;
    }}
    .features h2 {{
        font-size: 24px;
        font-weight: 600;
        margin-bottom: 10px;
        color: #2B2B2B;
        border-bottom: 0.5pt dashed #ddd;
        padding-bottom: 6px;
    }}
    .features ul {{
        padding-left: 24px;
        font-size: 24px;
        line-height: 1.8;
        margin: 0;
    }}
    .features ul li {{
        margin-bottom: 6px;
    }}
    .description {{
        font-size: 24px;
        line-height: 1.9;
        color: #444;
        background: #fff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 18px;
    }}
    .info-section {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
    }}
    .info-box {{
        flex: 1;
        font-size: 22px;
        background: #f9f9f9;
        border-radius: 8px;
        padding: 12px 14px;
        border: 1px solid #e0e0e0;
    }}
    .info-box strong {{
        font-weight: 600;
        margin-right: 8px;
    }}
    .color-dot {{
        display:inline-block;
        width:10px;
        height:10px;
        border-radius:50%;
        background:#2B2B2B;
        margin-right:6px;
    }}
    .material-square {{
        display:inline-block;
        width:10px;
        height:10px;
        background:#999;
        margin-right:6px;
    }}
</style>
</head>
<body>
<div class="card">
    <h1>{product_name}</h1>
    <div class="top-section">
        <div class="product-img">
            <img src="{image_path}" alt="{product_name}">
        </div>
        <div class="features">
            <h2>主要特点</h2>
            <ul>{features}</ul>
        </div>
    </div>
    <div class="description"><strong>商品描述：</strong><br>{description}</div>
    <div class="info-section">
        <div class="info-box"><strong>颜色：</strong><span class="color-dot"></span>{color}</div>
        <div class="info-box"><strong>材质：</strong><span class="material-square"></span>{material}</div>
        <div class="info-box"><strong>编码：</strong>{code}</div>
    </div>
</div>
</body>
</html>
"""

# === 工具函数 ===
def parse_txt(txt_path):
    data = {}
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                key, val = line.split(":", 1)
                data[key.strip()] = val.strip()
    return data

def find_image_path(code, image_dir: Path, brand: str):
    cfg = BRAND_CONFIG.get(brand.lower(), {})
    priority = cfg.get("IMAGE_DES_PRIORITY", ["F", "C", "1", "01"])

    if not image_dir.exists():
        return PLACEHOLDER_IMG

    # ==== Clarks-Jingya 特殊逻辑：取最大数字后缀的图片 ====
    if brand.lower() == "clarks_jingya":
        pattern = re.compile(rf"^{re.escape(code)}_(\d+)\.jpg$", re.IGNORECASE)
        max_num = -1
        best_file = None

        for img_file in image_dir.glob(f"{code}_*.jpg"):
            m = pattern.match(img_file.name)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
                    best_file = img_file

        if best_file:
            return best_file.resolve().as_uri()

        return PLACEHOLDER_IMG

    # ==== 其他品牌：原逻辑 ====
    for suffix in priority:
        candidate = image_dir / f"{code}_{suffix}.jpg"
        if candidate.exists():
            return f"file:///{candidate.as_posix()}"

    return PLACEHOLDER_IMG


def extract_features(description_en):
    if not description_en:
        return []
    description_en = re.sub(r"<[^>]*>", "", description_en)
    first_sentence = description_en.split(".")[0]
    parts = re.split(r",| and ", first_sentence)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        clean_en = sanitize_text(p)
        zh = safe_translate(clean_en)
        zh_clean = sanitize_text(zh)
        if zh_clean:
            out.append(zh_clean)
    return out

def generate_html(data, output_path, image_dir, brand):
    product_name = data.get("Product Name", "")

    # 描述
    raw_desc_en = data.get("Product Description", "")
    clean_desc_en = sanitize_text(raw_desc_en)
    description_zh = sanitize_text(safe_translate(clean_desc_en))

    gender = data.get("Product Gender", "")
    color = data.get("Product Color", "")

    # 材质
    raw_mat = data.get("Product Material", "")
    clean_mat_en = sanitize_text(raw_mat)
    material = sanitize_text(safe_translate(clean_mat_en, target_lang="ZH"))

    code = data.get("Product Code", "")
    image_path = find_image_path(code, image_dir, brand)

    # 特性
    feature_field = data.get("Feature", "")
    if feature_field and feature_field.lower() != "no data":
        raw_features = [f.strip() for f in feature_field.split("|") if f.strip()]

        # 先清英文敏感词 → 翻译 → 再清中文敏感词/正面化替换
        zh_features = [
            sanitize_text(  # 二次清理（中文阶段：可回收 → 环保材质等）
                safe_translate(  # 翻译到中文
                    sanitize_text(f)  # 一次清理（英文阶段：100% 等）
                )
            )
            for f in raw_features
        ]

        # 统一再做一次清理+去重（保险起见）
        feature_list = sanitize_features(zh_features)
    else:
        feature_list = extract_features(clean_desc_en)  # 这里已在函数内做了前后清理

    features_html = "".join([f"<li>{f}</li>" for f in feature_list])

    html = HTML_TEMPLATE.format(
        product_name=product_name,
        image_path=image_path,
        description=description_zh,
        color=color,
        gender=gender,
        material=material,
        code=code,
        features=features_html
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path

# === 多线程处理 ===
def process_file(txt_file, image_dir, html_dir, brand):
    try:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}.html"
        generate_html(data, output_file, image_dir, brand)
        return f"✅ {output_file.name}"
    except Exception as e:
        return f"❌ {txt_file.name}: {e}"

def main(brand=None, max_workers=4):
    if brand is None:
        if len(sys.argv) < 2:
            print("❌ 用法: python generate_html.py [brand]")
            return
        brand = sys.argv[1].lower()
    else:
        brand = brand.lower()

    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置: {brand}")
        return

    cfg = BRAND_CONFIG[brand]
    txt_dir = cfg["TXT_DIR"]
    image_dir = cfg["IMAGE_DIR"]
    html_dir = cfg["HTML_DIR_DES"]
    html_dir.mkdir(parents=True, exist_ok=True)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 未找到 TXT 文件: {txt_dir}")
        return

    print(f"开始处理 {len(files)} 个文件，使用 {max_workers} 个线程...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_file, txt_file, image_dir, html_dir, brand): txt_file
            for txt_file in files
        }
        for future in as_completed(futures):
            print(future.result())

    print(f"✅ 所有 HTML 已生成到：{html_dir}")

if __name__ == "__main__":
    main()
