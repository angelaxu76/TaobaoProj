import sys
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from common.text.translate import safe_translate
from common.text.ad_sanitizer import sanitize_text, sanitize_features
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

    /* 自适应图片：宽度100%，不裁图，容器可缩放 */
/* 左右区域：不拉伸等高，图片列更宽 */
.top-section{{
    display:flex;
    gap:24px;
    margin-bottom:28px;
    align-items:flex-start;  /* 关键：避免把左列拉到与右列等高 */
}}

/* 自适应图片：更大的左列 */
.product-img{{
    flex:2;                 /* 原来是 1，改成 3 → 左列更宽 */
    min-width:0;
    background:#fafafa;
    border-radius:10px;
    border:1px solid #e0e0e0;
    padding:0;
    overflow:hidden;
    display:block;
}}

/* 右侧特性列相对变窄 */
.features{{
    flex:2;                 /* 原来是 1，改成 2 */
}}

/* 图片尽量大且不裁图 */
.product-img img{{
    display:block;
    width:100%;
    height:auto;            /* 等比缩放 */
    max-height:90vh;        /* 原来 70vh → 90vh（需要更高可调大或去掉这一行） */
    object-fit:contain;     /* 不裁图 */
    border-radius:8px;
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
       <!-- <div class="info-box"><strong>材质：</strong><span class="material-square"></span>{material}</div> -->
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
    if brand.lower() == "clarks":
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
        sep = BRAND_CONFIG.get(brand, {}).get("FEATURE_DELIMITER", "|")
        raw_features = [f.strip() for f in feature_field.split(sep) if f.strip()]

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

    # —— 生成 html 字符串前的健诊 ——
    try:
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
    except Exception as fe:
        raise RuntimeError(f"HTML_TEMPLATE.format 失败：{fe}")

    # —— 确保目录存在（即使上层传错了）——
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # —— 实际写文件 ——
    with open(output_path, "w", encoding="utf-8") as f:
        n = f.write(html)

    # —— 写出后二次校验 ——
    p = Path(output_path)
    if not p.exists():
        raise IOError(f"写出后文件不存在：{p}")
    if n == 0 or p.stat().st_size == 0:
        raise IOError(f"写出后文件为空：{p}")

    return output_path


# === 多线程处理 ===
def process_file(txt_file, image_dir, html_dir, brand):
    try:
        data = parse_txt(txt_file)
        code = data.get("Product Code", txt_file.stem)
        output_file = html_dir / f"{code}_Details.html"
        generate_html(data, output_file, image_dir, brand)
        return f"✅ {output_file.name}"
    except Exception as e:
        return f"❌ {txt_file.name}: {e}"

def generate_html_main(brand=None, max_workers=4):
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

# === 辅助：规范化编码（便于匹配 TXT 与图片名） ===
def _norm_code(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (s or "").upper())

# === 从文件名里猜编码（适配 Barbour / Camper 常见命名）===
def _guess_code_from_filename(name: str) -> str:
    stem = Path(name).stem
    # 去掉末尾的 _数字（如 _1, _2）
    stem = re.sub(r"_[0-9]+$", "", stem)

    # 优先匹配 Barbour：如 LWX0667SG91 / MWX2507BK71
    m = re.search(r"[A-Z]{3}\d{4}[A-Z]{2}\d{2}", stem)
    if m:
        return m.group(0).upper()

    # 兼容 Camper：如 K100300-001 / K100300_001
    m = re.search(r"[A-Z]\d{6}[-_]\d{3}", stem)
    if m:
        return m.group(0).replace("_", "-").upper()

    # 回退：取开头到第一个 '-' 或 '_' 之前的段
    token = re.split(r"[-_]", stem)[0]
    return token.upper()

# === 扫描图片目录，收集去重后的编码集合 ===
def _collect_codes_from_images(image_dir: Path) -> list[str]:
    if not image_dir.exists():
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    codes = set()
    for p in image_dir.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            code = _guess_code_from_filename(p.name)
            if code:
                codes.add(code)
    # 稍微排序：字母优先、再自然序
    return sorted(codes, key=lambda x: (x[0], x))

# === 只根据图片目录中的编码来生成 HTML ===
def generate_html_from_images(brand: str, max_workers: int = 4):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置: {brand}")
        return

    cfg = BRAND_CONFIG[brand]
    image_dir = cfg["IMAGE_DIR"]      # 读取图片目录
    txt_dir   = cfg["TXT_DIR"]        # TXT 目录
    html_dir  = cfg["HTML_DIR_DES"]   # 输出目录
    html_dir.mkdir(parents=True, exist_ok=True)

    # 1) 从图片名解析编码并去重
    codes = _collect_codes_from_images(image_dir)
    if not codes:
        print(f"❌ {image_dir} 中未发现可解析的图片文件名")
        return
    print(f"🔎 从图片目录收集到 {len(codes)} 个编码。示例：{codes[:5]}")

    # 2) 建立 TXT 索引（按编码匹配）
    txt_index = {}
    for txt in txt_dir.glob("*.txt"):
        try:
            d = parse_txt(txt)
            code_in_txt = d.get("Product Code", "") or txt.stem
            txt_index[_norm_code(code_in_txt)] = txt
        except Exception:
            # 即使个别 TXT 解析失败也不要影响其它
            continue

    # 3) 用图片得到的编码去筛选 TXT 列表
    selected_txts = []
    missing_codes = []
    for c in codes:
        key = _norm_code(c)
        if key in txt_index:
            selected_txts.append(txt_index[key])
        else:
            missing_codes.append(c)

    if not selected_txts:
        print(f"❌ 根据图片解析的编码，在 {txt_dir} 未匹配到任何 TXT")
        if missing_codes:
            print("   （示例缺失编码）", missing_codes[:10])
        return

    if missing_codes:
        print(f"⚠️ 有 {len(missing_codes)} 个编码在 TXT 目录中缺失，已跳过。示例：{missing_codes[:10]}")

    # 4) 复用原有多线程处理逻辑，仅对筛中的 TXT 生成
    print(f"开始处理 {len(selected_txts)} 个文件，使用 {max_workers} 个线程.")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_file, txt_file, image_dir, html_dir, brand): txt_file
            for txt_file in selected_txts
        }
        for future in as_completed(futures):
            print(future.result())

    print(f"✅ 所有 HTML 已生成到：{html_dir}")


# === 从商品编码列表生成 HTML（编码来自一个txt文件）===
def _read_codes_file(codes_file: Path) -> list[str]:
    """
    读取包含商品编码的文件。优先使用 .txt，如果 .txt 不存在则尝试同名 .xlsx。
    支持：一行一个编码；或逗号/空格分隔；自动忽略空行与注释(#开头)。
    """
    codes_file = Path(codes_file)
    # 优先 txt，fallback xlsx
    if not codes_file.exists():
        alt = codes_file.with_suffix(".xlsx") if codes_file.suffix.lower() == ".txt" else codes_file.with_suffix(".txt")
        if alt.exists():
            print(f"⚠️  {codes_file.name} 不存在，改用 {alt.name}")
            codes_file = alt
        else:
            print(f"❌ 编码文件不存在：{codes_file}")
            return []

    import re
    codes = []
    if codes_file.suffix.lower() == ".xlsx":
        import pandas as pd
        df = pd.read_excel(codes_file, sheet_name=0, usecols=[0], header=0)
        for val in df.iloc[:, 0].dropna():
            p = str(val).strip()
            if p:
                codes.append(p)
    else:
        with open(codes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 支持一行多个：逗号/空格/制表符分隔
                parts = re.split(r"[,\s]+", line)
                for p in parts:
                    p = p.strip()
                    if p:
                        codes.append(p)
    # 去重并保持顺序
    seen = set()
    ordered = []
    for c in codes:
        k = _norm_code(c)
        if k not in seen:
            seen.add(k)
            ordered.append(c)
    return ordered


def generate_html_from_codes_files(brand: str, codes_file: str | Path, max_workers: int = 4):
    """
    根据“商品编码列表txt”选择对应TXT并生成HTML。
    路径与 generate_html_from_images 一致：读取 BRAND_CONFIG[brand] 的 TXT/IMAGE/HTML 目录。
    :param brand: 品牌名（如 'camper', 'barbour', 'clarks'）
    :param codes_file: 商品编码列表txt路径（如 D:\\TB\\Products\\camper\\repulibcation\\publication_codes.txt）
    :param max_workers: 线程数
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置: {brand}")
        return

    cfg = BRAND_CONFIG[brand]
    image_dir = cfg["IMAGE_PROCESS"]      # 读取图片目录
    txt_dir   = cfg["TXT_DIR"]        # TXT 目录
    html_dir  = cfg["HTML_DIR_DES"]   # 输出目录
    html_dir.mkdir(parents=True, exist_ok=True)

    codes_path = Path(codes_file)
    codes_raw = _read_codes_file(codes_path)
    if not codes_raw:
        print(f"❌ 在编码文件中未读取到有效编码：{codes_path}")
        return
    # 规范化后的键
    code_keys = [_norm_code(c) for c in codes_raw]
    print(f"🔎 从编码文件收集到 {len(code_keys)} 个编码。示例：{codes_raw[:5]}")

    # 建立 TXT 索引（以“规范化后的编码”为键）
    txt_index = {}
    for txt in txt_dir.glob("*.txt"):
        try:
            d = parse_txt(txt)
            code_in_txt = d.get("Product Code", "")
            if not code_in_txt:
                # 兜底：从文件名猜
                code_in_txt = _guess_code_from_filename(txt.name)
            key = _norm_code(code_in_txt)
            if key:
                # 若重复，保留先入（通常无影响）
                txt_index.setdefault(key, txt)
        except Exception:
            continue

    # 用编码列表筛选 TXT
    selected_txts, missing_codes = [], []
    for k, raw in zip(code_keys, codes_raw):
        if k in txt_index:
            selected_txts.append(txt_index[k])
        else:
            missing_codes.append(raw)

    if not selected_txts:
        print(f"❌ 根据提供的编码，在 {txt_dir} 未匹配到任何 TXT")
        if missing_codes:
            print("   （示例缺失编码）", missing_codes[:10])
        return

    if missing_codes:
        print(f"⚠️ 有 {len(missing_codes)} 个编码在 TXT 目录中缺失，已跳过。示例：{missing_codes[:10]}")

    # 复用原有多线程处理逻辑
    print(f"开始处理 {len(selected_txts)} 个文件，使用 {max_workers} 个线程.")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_file, txt_file, image_dir, html_dir, brand): txt_file
            for txt_file in selected_txts
        }
        for future in as_completed(futures):
            print(future.result())

    print(f"✅ 所有 HTML 已生成到：{html_dir}")

