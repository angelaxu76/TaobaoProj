import sys
import re
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from common_taobao.core.translate import safe_translate
from config import BRAND_CONFIG

PLACEHOLDER_IMG = "https://via.placeholder.com/500x500?text=No+Image"
AD_WORDS_FILE = Path(r"D:\TB\Products\config\ad_sensitive_words.txt")

# === 加载敏感词 ===
def load_sensitive_words():
    if AD_WORDS_FILE.exists():
        with open(AD_WORDS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    else:
        print(f"⚠️ 未找到敏感词文件，使用默认列表")
        return ["国家级", "世界级", "顶级", "最佳", "绝对", "唯一", "独家", "首个", "第一", "最先进", "最优", "最高级",
                "极致", "至尊", "顶尖", "终极", "空前", "史上最", "无敌", "完美", "王牌", "冠军", "首选", "权威", "专家推荐",
                "全球领先", "全国领先"]

SENSITIVE_WORDS = load_sensitive_words()

def clean_ad_sensitive(text: str) -> str:
    for word in SENSITIVE_WORDS:
        text = text.replace(word, "")
    return text.strip()

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
        font-size: 18px;
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
        <div class="info-box"><strong>性别：</strong>{gender}</div>
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

def find_image_path(code, image_dir):
    img_f = image_dir / f"{code}_F.jpg"
    img_c = image_dir / f"{code}_C.jpg"
    if img_f.exists():
        return f"file:///{img_f.as_posix()}"
    elif img_c.exists():
        return f"file:///{img_c.as_posix()}"
    return PLACEHOLDER_IMG

def extract_features(description_en):
    if not description_en:
        return []
    description_en = re.sub(r"<[^>]*>", "", description_en)
    first_sentence = description_en.split(".")[0]
    parts = re.split(r",| and ", first_sentence)
    return [clean_ad_sensitive(safe_translate(p.strip())) for p in parts if p.strip()]

def generate_html(data, output_path, image_dir):
    product_name = data.get("Product Name", "")
    description_en = data.get("Product Description", "")
    description_zh = clean_ad_sensitive(safe_translate(description_en))
    gender = data.get("Product Gender", "")
    color = data.get("Product Color", "")
    material = data.get("Product Material", "")
    code = data.get("Product Code", "")
    image_path = find_image_path(code, image_dir)

    feature_field = data.get("Feature", "")
    if feature_field and feature_field.lower() != "no data":
        feature_list = [clean_ad_sensitive(safe_translate(f.strip())) for f in feature_field.split("|") if f.strip()]
    else:
        feature_list = extract_features(description_en)

    features_html = "".join([f"<li>{f}</li>" for f in feature_list])

    html = HTML_TEMPLATE.format(
        product_name=product_name,
        image_path=image_path,
        description=description_zh,
        color=color,
        gender=gender,
        material=material,
        features=features_html
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path

# === 多线程处理 ===
def process_file(txt_file, image_dir, html_dir):
    try:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}.html"
        generate_html(data, output_file, image_dir)
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
    html_dir = cfg["HTML_DIR"]
    html_dir.mkdir(parents=True, exist_ok=True)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 未找到 TXT 文件: {txt_dir}")
        return

    print(f"开始处理 {len(files)} 个文件，使用 {max_workers} 个线程...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file, txt_file, image_dir, html_dir): txt_file for txt_file in files}
        for future in as_completed(futures):
            print(future.result())

    print(f"✅ 所有 HTML 已生成到：{html_dir}")

if __name__ == "__main__":
    main()
