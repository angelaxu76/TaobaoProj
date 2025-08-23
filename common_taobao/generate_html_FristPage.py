import sys
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import BRAND_CONFIG

# ===== 可调参数 =====
PLACEHOLDER_IMG = "https://via.placeholder.com/750x563?text=No+Image"  # 4:3
IMAGE_PRIORITY_DEFAULT = ["F", "C", "1",
                          "01"]  # 查找图片优先级：CODE_F.jpg → CODE_C.jpg → CODE_1.jpg → CODE_01.jpg → CODE.jpg → CODE.png

# ===== 内置首屏 HTML 模板（来自你上传的首屏.html，未改动结构样式）=====
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>首屏｜极简高质感升级版</title>
<style>
  :root{
    --w:750px; --pad:28px;
    --fz:30px;         /* 四行主文字号（手机端直读） */
    --lh:1.5;          /* 行高 */
    --gap:10px;        /* 行间距 */
    --text:#111; --muted:#667085; --bg:#F6F7FA; --card:#fff; --line:#E6E8EC;
    --accent:#6B4EFF;  /* 只在关键数字/关键词上使用的点睛色 */
  }
  html,body{
    margin:0; background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .card{
    width:var(--w); margin:16px auto; background:var(--card);
    border-radius:18px; box-shadow:0 6px 18px rgba(0,0,0,.05); overflow:hidden;
    border:1px solid #F1F2F4;
  }
  /* 主图 */
    .media{ background:#fff; }
    .media img{
      display:block;
      width:100%;
      height:auto;            /* 让图片按原比例自适应高度 */
      /* 删除 aspect-ratio 与 object-fit */
    }


  /* 文案区 */
  .body{ padding:18px var(--pad) 24px; }
  .list{ list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:var(--gap); }
  .item{ display:flex; align-items:flex-start; gap:12px; }
  .ico{ width:36px; flex:0 0 36px; text-align:center; font-size:28px; line-height:1.1; margin-top:2px; }
  .txt{ font-size:var(--fz); line-height:var(--lh); font-weight:700; letter-spacing:0; }

  /* 关键强调：只在极少处使用，保持克制与高级感 */
  .accent{ color:var(--accent); font-weight:800; }

  /* 细节：段落间细分隔（可去掉） */
  .body::before{ content:""; display:block; height:1px; background:var(--line); margin-bottom:14px; }
</style>
</head>
<body>
  <section class="card" data-mod="hero">
    <!-- 主图：替换为你的图片路径 -->
    <div class="media">
      <img src="__IMAGE_URL__" alt="商品主图">
    </div>

    <div class="body">
        <ul class="list">
          <li class="item">
            <span class="ico">🌐</span>
            <span class="txt">官网直采 · 凭证俱全</span>
          </li>
          <li class="item">
            <span class="ico">📦</span>
            <span class="txt">英国直邮 · 关税预付</span>
          </li>
          <li class="item">
            <span class="ico">🚚</span>
            <span class="txt">清关无忧 · 淘宝菜鸟平台代办</span>
          </li>
          <li class="item">
            <span class="ico">🛡️</span>
            <span class="txt">8年老店 · 正品保障 · 假一赔三</span>
          </li>
          <li class="item">
            <span class="ico">📏</span>
            <span class="txt"><span class="accent">10,000+</span> 客户荐码 · 尺码不合适可协商解决</span>
          </li>
        </ul>
    </div>
  </section>
</body>
</html>
"""


def render_template(image_url: str) -> str:
    """把模板中的占位符 __IMAGE_URL__ 替换为真实图片路径"""
    return HTML_TEMPLATE.replace("__IMAGE_URL__", image_url, 1)


def _code_variants(code: str) -> list[str]:
    """基于原始编码构造多种文件名变体用于匹配图片。"""
    raw = code.strip()
    no_sep = re.sub(r"[^A-Za-z0-9]", "", raw)
    under = raw.replace("-", "_")
    # 去掉末尾 _数字（如 _1）
    raw_trim = re.sub(r"_[0-9]+$", "", raw)
    under_trim = re.sub(r"_[0-9]+$", "", under)
    no_sep_trim = re.sub(r"_[0-9]+$", "", no_sep)
    # 去重保持顺序
    seen = set()
    out = []
    for v in [raw, raw_trim, under, under_trim, no_sep, no_sep_trim]:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

def find_image_url(code: str, image_dir: Path, priority: list[str]) -> str:
    if not image_dir.exists():
        return PLACEHOLDER_IMG

    exts = [".jpg", ".jpeg", ".png", ".webp"]
    variants = _code_variants(code)

    # 1) 先按变体+优先级+扩展名精确匹配
    for v in variants:
        for suf in priority:
            for e in exts:
                for pat in (f"{v}_{suf}{e}", f"{v}-{suf}{e}", f"{v}{suf}{e}"):
                    p = image_dir / pat
                    if p.exists():
                        return p.resolve().as_uri()

        for e in exts:
            p = image_dir / f"{v}{e}"
            if p.exists():
                return p.resolve().as_uri()

    # 2) 兜底：任意以任一变体开头的图片文件
    for v in variants:
        for p in sorted(image_dir.glob(f"{v}*")):
            if p.is_file() and p.suffix.lower() in exts:
                return p.resolve().as_uri()

    return PLACEHOLDER_IMG



def process_one(display_code: str, image_dir: Path, out_dir: Path, priority: list[str]):
    """
    display_code: 原始编码（保留连字符），用于输出文件名。
    找图时会自动尝试多种变体（带 -、带 _、无分隔）。
    """
    img_url = find_image_url(display_code, image_dir, priority)
    html = render_template(img_url)
    out_path = out_dir / f"{display_code}_First.html"   # ✅ 保留连字符
    out_path.write_text(html, encoding="utf-8")
    return f"✅ {out_path.name}"



def generate_html_for_first_page(brand: str, max_workers: int = 6):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置：{brand}")
        return

    cfg = BRAND_CONFIG[brand]
    txt_dir: Path = cfg["TXT_DIR"]
    image_dir: Path = cfg["IMAGE_PROCESS"]
    html_dir: Path = cfg.get("HTML_DIR", Path.cwd() / "HTML")
    hero_dir: Path = cfg.get("HTML_DIR_FIRST_PAGE")
    hero_dir.mkdir(parents=True, exist_ok=True)

    priority = cfg.get("IMAGE_FIRST_PRIORITY", IMAGE_PRIORITY_DEFAULT)

    files = list(txt_dir.glob("*.txt"))
    if not files:
        print(f"❌ 没找到 TXT 文件：{txt_dir}")
        return
    codes = [f.stem for f in files]

    print(f"▶ 生成首屏 HTML：brand={brand}，codes={len(codes)}，输出目录={hero_dir}")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(process_one, code, image_dir, hero_dir, priority)
            for code in codes
        ]
        for f in as_completed(futs):
            print(f.result())
    print("✅ 全部完成。")

# === 新增：规范化 & 从文件名猜编码 ===
def _norm_code(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (s or "").upper())

def _guess_code_from_filename(name: str) -> str:
    stem = Path(name).stem
    # 去末尾 _数字（如 _1, _2）
    stem = re.sub(r"_[0-9]+$", "", stem)

    # Barbour: LWX0667SG91 / MWX2507BK71
    m = re.search(r"[A-Z]{3}\d{4}[A-Z]{2}\d{2}", stem)
    if m:
        return m.group(0).upper()

    # Camper: K100300-001 / K100300_001
    m = re.search(r"[A-Z]\d{6}[-_]\d{3}", stem)
    if m:
        return m.group(0).replace("_", "-").upper()

    # 回退：取第一个分隔段
    token = re.split(r"[-_]", stem)[0]
    return token.upper()

def _collect_codes_from_images(image_dir: Path) -> list[str]:
    if not image_dir or not image_dir.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    codes = set()
    for p in image_dir.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            code = _guess_code_from_filename(p.name)
            if code:
                codes.add(code)
    return sorted(codes)

def _get_image_dir(cfg: dict) -> Path:
    # 优先使用 IMAGE_DIR（document/images），没有就退回 IMAGE_PROCESS
    return cfg.get("IMAGE_DIR") or cfg.get("IMAGE_PROCESS") or Path.cwd()

# === 修改：find_image_url 更鲁棒（加多后缀 & 最后兜底选任意匹配）===
def find_image_url(code: str, image_dir: Path, priority: list[str]) -> str:
    if not image_dir.exists():
        return PLACEHOLDER_IMG

    # 先按优先级尝试
    exts = [".jpg", ".jpeg", ".png", ".webp"]
    candidates = []
    for suf in priority:
        candidates += [image_dir / f"{code}_{suf}{e}" for e in exts]
        candidates += [image_dir / f"{code}-{suf}{e}" for e in exts]
        candidates += [image_dir / f"{code}{suf}{e}" for e in exts]
    candidates += [image_dir / f"{code}{e}" for e in exts]

    for c in candidates:
        if c.exists():
            return c.resolve().as_uri()

    # 兜底：找任意以 code 开头的图片文件
    for p in sorted(image_dir.glob(f"{code}*")):
        if p.suffix.lower() in exts and p.is_file():
            return p.resolve().as_uri()

    return PLACEHOLDER_IMG

# === 新增：从图片目录收集编码并生成首屏 HTML（不依赖 TXT） ===
def generate_first_page_from_images(brand: str, max_workers: int = 6):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置：{brand}")
        return

    cfg = BRAND_CONFIG[brand]
    image_dir: Path = _get_image_dir(cfg)
    hero_dir: Path = cfg.get("HTML_DIR_FIRST_PAGE") or (Path.cwd() / "HTML_FIRST_PAGE")
    hero_dir.mkdir(parents=True, exist_ok=True)
    priority = cfg.get("IMAGE_FIRST_PRIORITY", IMAGE_PRIORITY_DEFAULT)

    # 1) 从图片名提取编码
    codes = _collect_codes_from_images(image_dir)
    if not codes:
        print(f"❌ {image_dir} 中未发现可解析的图片文件名")
        return

    print(f"▶ 生成首屏 HTML（按图片目录驱动）：brand={brand}，发现编码={len(codes)}，输出目录={hero_dir}")
    # 2) 生成 HTML
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(process_one, code, image_dir, hero_dir, priority) for code in codes]
        for f in as_completed(futs):
            print(f.result())
    print("✅ 全部完成。")


if __name__ == "__main__":
    """
    用法：
      python make_hero_html_inline.py camper
    """
    if len(sys.argv) < 2:
        print("用法：python make_hero_html_inline.py [brand]")
        sys.exit(1)
    brand = sys.argv[1]
    generate_html_for_first_page(brand)


# === 读取商品编码列表（txt）===
def _read_codes_file(codes_file: Path) -> list[str]:
    """
    读取一个包含商品编码的txt文件。
    支持：一行一个编码；或逗号/空格/制表符分隔；自动忽略空行与 # 注释行。
    返回：去重且保持顺序的编码列表（原样保留大小写，但内部匹配用 _norm_code）
    """
    import re
    codes_raw = []
    if not codes_file.exists():
        print(f"❌ 编码文件不存在：{codes_file}")
        return codes_raw

    with open(codes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"[,\s]+", line)
            for p in parts:
                if p:
                    codes_raw.append(p.strip())

    # 去重并保持顺序（按规范化键判断）
    seen = set()
    ordered = []
    for c in codes_raw:
        k = _norm_code(c)
        if k and k not in seen:
            seen.add(k)
            ordered.append(c)
    return ordered


def generate_first_page_from_codes_files(brand: str, codes_file: str | Path, max_workers: int = 6):
    """
    根据“商品编码列表txt”生成首屏 HTML。
    图片与输出目录沿用 BRAND_CONFIG[brand]（与 generate_html_for_first_page 一致）。
    :param brand: 品牌（如 'camper', 'barbour', 'clarks_jingya'）
    :param codes_file: 商品编码列表txt路径（如 D:\\TB\\Products\\camper\\repulibcation\\publication_codes.txt）
    :param max_workers: 线程数
    """
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        print(f"❌ 未找到品牌配置：{brand}")
        return

    cfg = BRAND_CONFIG[brand]
    image_dir: Path = _get_image_dir(cfg)
    hero_dir: Path = cfg.get("HTML_DIR_FIRST_PAGE") or (Path.cwd() / "HTML_FIRST_PAGE")
    hero_dir.mkdir(parents=True, exist_ok=True)
    priority = cfg.get("IMAGE_FIRST_PRIORITY", IMAGE_PRIORITY_DEFAULT)

    codes_path = Path(codes_file)
    codes_raw = _read_codes_file(codes_path)
    if not codes_raw:
        print(f"❌ 在编码文件中未读取到有效编码：{codes_path}")
        return

    print(f"▶ 生成首屏 HTML（按编码列表驱动）：brand={brand}，编码数={len(codes_raw)}，输出目录={hero_dir}")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(process_one, code, image_dir, hero_dir, priority)
            for code in codes_raw
        ]
        for f in as_completed(futs):
            print(f.result())
    print("✅ 全部完成。")
