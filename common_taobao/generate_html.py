import sys
import re
from pathlib import Path
from common_taobao.core.translate import safe_translate
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
    body {{ font-family:"Comic Sans MS","微软雅黑",sans-serif;background:#f6f9fc;display:flex;justify-content:center;padding:30px; }}
    .card {{ width:700px;background:#fff;border-radius:20px;box-shadow:0 8px 20px rgba(0,0,0,0.1);padding:20px;display:flex;flex-direction:column;gap:20px; }}
    .card h1 {{ text-align:center;font-size:28px;color:#2c3e50; }}
    .top-section {{ display:flex;gap:20px; }}
    .product-img {{ flex:1;background:#e3f8e0;border-radius:15px;display:flex;align-items:center;justify-content:center;padding:15px; }}
    .product-img img {{ max-width:100%;border-radius:10px; }}
    .features {{ flex:1;background:#f9f9f9;border-radius:15px;padding:15px; }}
    .features h2 {{ font-size:20px;margin-bottom:10px; }}
    .features ul {{ padding-left:20px;font-size:16px;line-height:1.8; }}
    .description {{ background:#fdfdfd;border-radius:10px;padding:15px;font-size:16px;line-height:1.6;color:#444; }}
    .info-section {{ display:grid;grid-template-columns:repeat(2,1fr);gap:10px; }}
    .info-box {{ background:#f0f9ff;border-radius:10px;padding:10px 15px;font-size:16px; }}
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
        <div class="info-box"><strong>颜色：</strong>{color}</div>
        <div class="info-box"><strong>性别：</strong>{gender}</div>
        <div class="info-box"><strong>材质：</strong>{material}</div>
        <div class="info-box"><strong>尺码：</strong>{size}</div>
    </div>
</div>
</body>
</html>
"""

def parse_txt(txt_path):
    data = {}
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                key, val = line.split(":", 1)
                data[key.strip()] = val.strip()
    return data

def find_image_path(code, image_dir):
    img_f = image_dir / f"{code}_F.jpg"
    img_c = image_dir / f"{code}_C.jpg"
    if img_f.exists():
        return img_f.as_posix()
    elif img_c.exists():
        return img_c.as_posix()
    return PLACEHOLDER_IMG

def extract_features(description_en):
    if not description_en:
        return []
    description_en = re.sub(r"<[^>]*>", "", description_en)
    first_sentence = description_en.split(".")[0]
    parts = re.split(r",| and ", first_sentence)
    features = []
    for p in parts:
        text = p.strip()
        if text:
            translated = safe_translate(text)
            features.append(translated)
    return features

def generate_html(data, output_path, image_dir):
    product_name = data.get("Product Name", "")
    description_en = data.get("Product Description", "")
    description_zh = safe_translate(description_en)
    gender = data.get("Product Gender", "")
    color = data.get("Product Color", "")
    material = data.get("Product Material", "")
    size = data.get("Product Size", "")
    code = data.get("Product Code", "")
    image_path = find_image_path(code, image_dir)

    features_html = "".join([f"<li>{f}</li>" for f in extract_features(description_en)])

    html = HTML_TEMPLATE.format(
        product_name=product_name,
        image_path=image_path,
        description=description_zh,
        color=color,
        gender=gender,
        material=material,
        size=size,
        features=features_html
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 生成 HTML: {output_path}")

def main():
    if len(sys.argv) < 2:
        print("❌ 用法: python generate_html.py [brand] (如: camper, clarks)")
        return

    brand = sys.argv[1].lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置: {brand}")
        return

    cfg = BRAND_CONFIG[brand]
    txt_dir = cfg["TXT_DIR"]
    image_dir = cfg["IMAGE_DIR"]
    html_dir = cfg["HTML_DIR"]
    html_dir.mkdir(parents=True, exist_ok=True)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 未找到 TXT 文件: {txt_dir}")
        return

    for txt_file in files:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}.html"
        generate_html(data, output_file, image_dir)

def main(brand=None):
    if brand is None:
        import sys
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
    html_dir = cfg["HTML_DIR"]
    html_dir.mkdir(parents=True, exist_ok=True)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 未找到 TXT 文件: {txt_dir}")
        return

    for txt_file in files:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}.html"
        generate_html(data, output_file, image_dir)

if __name__ == "__main__":
    main()
