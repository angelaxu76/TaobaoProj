import sys
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from common.text.translate import safe_translate
from config import BRAND_CONFIG

AD_WORDS_FILE = Path(r"D:\TB\Products\config\ad_sensitive_words.txt")


def load_sensitive_words():
    if AD_WORDS_FILE.exists():
        with open(AD_WORDS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    else:
        return ["国家级", "世界级", "顶级", "最佳", "绝对", "唯一", "独家", "首个", "第一", "最先进", "最优", "最高级",
                "极致", "至尊", "顶尖", "终极", "空前", "史上最", "无敌", "完美", "王牌", "冠军", "首选", "权威",
                "专家推荐",
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
        background: #f1f3f8;
        margin: 0;
        padding: 32px 16px;
        display: flex;
        justify-content: center;
        color: #2c3e50;
        font-size: 18px;
    }}
    .card {{
        max-width: 820px;
        width: 100%;
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
        padding: 36px;
        box-sizing: border-box;
        border-top: 6px solid #5B8DEF;
    }}
    .card h1 {{
        font-size: 30px;
        font-weight: bold;
        color: #1d3557;
        margin-bottom: 24px;
        border-bottom: 1px dashed #ccc;
        padding-bottom: 12px;
    }}
    .features {{
        background: #f6faff;
        border-left: 5px solid #5B8DEF;
        padding: 18px 24px;
        border-radius: 10px;
        margin-bottom: 24px;
    }}
    .features h2 {{
        font-size: 22px;
        font-weight: 600;
        margin-bottom: 12px;
        color: #2c3e50;
    }}
    .features ul {{
        padding-left: 20px;
        margin: 0;
        font-size: 18px;
        line-height: 1.8;
    }}
    .features li {{
        margin-bottom: 6px;
    }}
    .description {{
        background: #fdfdfd;
        border: 1px solid #dce3ea;
        border-radius: 10px;
        padding: 20px 24px;
        font-size: 18px;
        line-height: 1.8;
        margin-bottom: 24px;
        color: #34495e;
    }}
    .description strong {{
        color: #2c3e50;
    }}
    .info-section {{
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
    }}
    .info-box {{
        flex: 1 1 200px;
        background: #f8f9fb;
        border-radius: 10px;
        padding: 14px 18px;
        font-size: 18px;
        color: #2b2b2b;
        border: 1px solid #e0e6ed;
    }}
    .info-box strong {{
        font-weight: 600;
        color: #5B8DEF;
        margin-right: 8px;
    }}
    @media (max-width: 640px) {{
        .card {{
            padding: 24px;
        }}
        .info-section {{
            flex-direction: column;
        }}
    }}
</style>
</head>
<body>
<div class="card">
    <h1>{product_name}</h1>
    <div class="features">
        <h2>主要特点</h2>
        <ul>{features}</ul>
    </div>
    <div class="description"><strong>商品描述：</strong><br>{description}</div>
<div class="info-section">
    <div class="info-box"><strong>尺码：</strong>{size_range}</div>
    <div class="info-box"><strong>商品编码：</strong>{product_code}</div>
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


def extract_features(description_en):
    if not description_en:
        return []
    description_en = re.sub(r"<[^>]*>", "", description_en)
    first_sentence = description_en.split(".")[0]
    parts = re.split(r",| and ", first_sentence)
    return [clean_ad_sensitive(safe_translate(p.strip())) for p in parts if p.strip()]


def round_up_to_10(n: float) -> int:
    return int(ceil(n / 10.0)) * 10


def extract_size_range(size_field: str) -> str:
    size_list = []
    for s in size_field.split(";"):
        s = s.strip()
        if "有货" in s:
            size_label = s.split(":")[0].strip().upper()
            size_list.append(size_label)

    if not size_list:
        return "尺码（单位）：无库存"

    # 字母尺码顺序
    standard_order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

    if all(re.fullmatch(r"\d+", s) for s in size_list):
        size_nums = sorted(int(s) for s in size_list)
        return f"尺码（单位：欧码）：{size_nums[0]}-{size_nums[-1]}"

    if all(s in standard_order for s in size_list):
        idx = [standard_order.index(s) for s in size_list]
        idx.sort()
        return f"尺码（单位：字母）：{standard_order[idx[0]]}-{standard_order[idx[-1]]}"

    return f"尺码（单位）：{'、'.join(size_list)}"


def generate_html(data, output_path):
    product_name = data.get("Product Name", "")
    description_en = data.get("Product Description", "")
    description_zh = clean_ad_sensitive(safe_translate(description_en))
    code = data.get("Product Code", output_path.stem)

    # 价格优先顺序
    try:
        price_gbp = float(
            data.get("Adjusted Price", "").replace("£", "").strip()
            or data.get("Price", "").replace("£", "").strip()
            or data.get("Product Price", "").replace("£", "").strip()
        )
        price_rmb = round_up_to_10(price_gbp * 1.3 * 9.8)
    except:
        price_rmb = 0

    # 尺码处理
    size_field = data.get("Product Size", "")
    size_range = extract_size_range(size_field)

    # 特点
    feature_field = data.get("Feature", "")
    if feature_field and feature_field.lower() != "no data":
        feature_list = [clean_ad_sensitive(safe_translate(f.strip())) for f in feature_field.split("|") if f.strip()]
    else:
        feature_list = extract_features(description_en)
    features_html = "".join([f"<li>{f}</li>" for f in feature_list])

    html = HTML_TEMPLATE.format(
        product_name=product_name,
        description=description_zh,
        features=features_html,
        size_range=size_range,
        price_rmb=price_rmb,
        product_code=code
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def process_file(txt_file, html_dir):
    try:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}.html"
        generate_html(data, output_file)
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
    html_dir = cfg["HTML_DIR"]
    html_dir.mkdir(parents=True, exist_ok=True)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 未找到 TXT 文件: {txt_dir}")
        return

    print(f"开始处理 {len(files)} 个文件，使用 {max_workers} 个线程...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file, txt_file, html_dir): txt_file for txt_file in files}
        for future in as_completed(futures):
            print(future.result())

    print(f"✅ 所有 HTML 已生成到：{html_dir}")


if __name__ == "__main__":
    main()
