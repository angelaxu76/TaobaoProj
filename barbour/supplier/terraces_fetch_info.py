# -*- coding: utf-8 -*-
"""
Terraces Menswear 商品信息抓取（与 very/houseoffraser 保持一致的字段与目录规范）
- 读取：config.BARBOUR["LINKS_FILES"]["terraces"]
- 输出：config.BARBOUR["TXT_DIRS"]["terraces"] / <CleanTitle>_<hash4>.txt
- 字段（顺序对齐 HOF/Very）：
  Product Code, Product Name, Product Description, Product Gender, Product Color,
  Product Price, Adjusted Price, Product Material, Style Category, Feature,
  Product Size, Product Size Detail, Source URL, Site Name
"""
import re
import json
import hashlib
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from barbour.core.site_utils import assert_site_or_raise as canon
from barbour.core.sim_matcher import match_product, choose_best, explain_results
from sqlalchemy import create_engine
from config import BARBOUR, BRAND_CONFIG


# ==== 浏览器兜底（与 very 同风格） ====
import shutil, subprocess, sys
import undetected_chromedriver as uc

# ===== 标准尺码表（用于补齐未出现尺码=0） =====
WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（不含 52）

def _full_order_for_gender(gender: str) -> list[str]:
    """根据性别返回完整尺码顺序；Terraces 站整体为男款，未知也按男款处理。"""
    g = (gender or "").lower()
    if "女" in g or "women" in g or "ladies" in g:
        return WOMEN_ORDER
    return MEN_ALPHA_ORDER + MEN_NUM_ORDER


def _get_chrome_major_version() -> int | None:
    try:
        import winreg
    except Exception:
        winreg = None
    if winreg is not None and sys.platform.startswith("win"):
        reg_paths = [
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon"),
        ]
        for hive, path in reg_paths:
            try:
                with winreg.OpenKey(hive, path) as k:
                    ver, _ = winreg.QueryValueEx(k, "version")
                    m = re.search(r"^(\d+)\.", ver)
                    if m:
                        return int(m.group(1))
            except OSError:
                pass
    for exe in ["chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]:
        path = shutil.which(exe) or exe
        try:
            out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT, text=True, timeout=3)
            m = re.search(r"(\d+)\.\d+\.\d+\.\d+", out)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None

def _get_uc_driver(headless: bool = True):
    def make_options():
        opts = uc.ChromeOptions()
        if headless: opts.add_argument("--headless=new")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        return opts
    last_err = None
    try:
        return uc.Chrome(options=make_options(), headless=headless, use_subprocess=True)
    except Exception as e:
        last_err = e
    try:
        vm = _get_chrome_major_version()
        if vm:
            return uc.Chrome(options=make_options(), headless=headless, use_subprocess=True, version_main=vm)
    except Exception as e2:
        last_err = e2
    raise last_err


PRODUCTS_TABLE: str = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]  # ✅ 注意这里


# 项目内的通用 TXT 写入（若存在则优先使用，字段/顺序将与全站一致）
try:
    from common_taobao.txt_writer import format_txt as write_txt
except Exception:
    write_txt = None  # 用本文件的 fallback 写盘

from config import BARBOUR  # 复用全局配置（含 LINKS_FILES / TXT_DIRS）

SUPPLIER_KEY  = "terraces"
SITE_NAME     = canon(SUPPLIER_KEY)   # ✅ 按 config 标准化
UA            = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/119.0.0.0 Safari/537.36")
HEADERS       = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

import random
import time
from urllib.parse import urljoin

UA_POOL = [
    # 挑几条常见桌面 UA 轮换
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
]
BASE_HOME = "https://www.terracesmenswear.co.uk/"
LISTING_REFERER = "https://www.terracesmenswear.co.uk/mens-outlet"

engine_url = (
    f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
    f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
)
_ENGINE = create_engine(engine_url)

def get_raw_connection():
    return _ENGINE.raw_connection()


# ==================== 工具函数 ====================
def _safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\s\-\_\.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "_")[:150] or "No_Data"

def _short_hash(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()[:4]

def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""

def _split_title_color(title: str) -> tuple[str, str | None]:
    """
    标题一般是 “Name - Color” 结构。
    返回 (净化后的标题, 颜色)，若无颜色返回 (原标题, None)
    """
    t = (title or "").strip()
    if not t:
        return "No Data", None
    parts = [p.strip() for p in re.split(r"\s*-\s*", t) if p.strip()]
    if len(parts) >= 2:
        raw_color = parts[-1]
        # 多词颜色仅取第一个主词（Beige/Stone -> Beige）
        color = re.split(r"[\/&]", re.sub(r"[^\w\s/&-]", "", raw_color))[0].strip()
        color = color.title() if color else None
        clean_title = " - ".join(parts[:-1])  # 去掉颜色尾巴
        return (clean_title or t, color or None)
    return t, None

def _parse_json_ld(soup: BeautifulSoup) -> dict:
    """
    解析页面中的 JSON-LD，返回最相关的 dict；失败返回 {}。
    """
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            obj = json.loads(tag.string or tag.get_text() or "{}")
            cand = obj[0] if isinstance(obj, list) and obj else obj
            if isinstance(cand, dict) and ("name" in cand or "offers" in cand or "color" in cand):
                return cand
        except Exception:
            continue
    return {}

# ==================== 尺码/库存抽取（DOM/JSON 多级策略） ====================
_SIZE_PAT = re.compile(
    r"\b(One Size|OS|XXS|XS|S|M|L|XL|XXL|3XL|4XL|5|6|7|8|9|10|11|12|13|28|30|32|34|36|38|40|42)\b",
    re.I
)

def _extract_sizes(soup: BeautifulSoup, gender: str) -> tuple[list[str], str]:
    """
    返回 (sizes_seen, size_detail)
    - sizes_seen: 网页上出现到的尺码列表（保持原样，便于兼容现有下游）
    - size_detail: 按完整尺码表输出，出现的尺码用 3/0，未出现的尺码补 0
    """
    sizes: list[str] = []
    avail: dict[str, int] = {}  # 1=有货, 0=无货

    # —— 1) product JSON（优先）
    for tag in soup.find_all("script", {"type": "application/json"}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw or "variants" not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        variants = data.get("variants")
        if isinstance(variants, list) and variants:
            size_idx = None
            options = data.get("options")
            if isinstance(options, list):
                for i, name in enumerate(options, 1):
                    if str(name).strip().lower() in ("size", "sizes"):
                        size_idx = i
                        break
            for v in variants:
                is_avail = 1 if (v.get("available") or v.get("is_available") or v.get("in_stock")) else 0
                sz = None
                for key in filter(None, [f"option{size_idx}" if size_idx else None, "option1", "option2", "option3", "title"]):
                    val = v.get(key)
                    if val:
                        m = _SIZE_PAT.search(str(val))
                        if m:
                            sz = m.group(0).strip()
                            break
                if sz:
                    if sz not in sizes:
                        sizes.append(sz)
                    # 有货优先：若之前标记无货，这里有货覆盖它
                    if avail.get(sz, -1) != 1:
                        avail[sz] = 1 if is_avail else 0
            if sizes:
                break

    # —— 2) DOM（回退）
    if not sizes:
        for lab in soup.select("label.size-wrap"):
            btn = lab.find("button", class_="size-box")
            if not btn:
                continue
            sz = (btn.get_text(" ", strip=True) or "").strip()
            if not sz or not _SIZE_PAT.search(sz):
                continue
            disabled = False
            inp = lab.find("input")
            if inp and (inp.has_attr("disabled") or str(inp.get("aria-disabled", "")).lower() == "true"):
                disabled = True
            cls = " ".join(lab.get("class", [])).lower()
            if "disabled" in cls or "sold" in cls:
                disabled = True
            if sz not in sizes:
                sizes.append(sz)
            if avail.get(sz, -1) != 1:
                avail[sz] = 0 if disabled else 1

    # —— 3) JSON-LD（兜底）
    if not sizes:
        jl = _parse_json_ld(soup)
        off = jl.get("offers")
        if isinstance(off, list):
            for o in off:
                k = (o.get("name") or o.get("sku") or "")
                m = _SIZE_PAT.search(str(k))
                if m:
                    sz = m.group(0)
                    if sz not in sizes:
                        sizes.append(sz)
                    if avail.get(sz, -1) != 1:
                        avail[sz] = 1 if "InStock" in str(o.get("availability", "")) else 0

    # ===== 统一补齐：按完整尺码表输出 Product Size Detail =====
    EAN = "0000000000000"
    full_order = _full_order_for_gender(gender)

    # 即使完全抓不到尺码，也输出完整 0 栅格，避免下游缺行
    if not sizes:
        detail = ";".join(f"{s}:0:{EAN}" for s in full_order)
        return [], detail

    # 已抓到部分尺码：出现的按 avail 写 3/0，未出现的补 0
    detail = ";".join(f"{s}:{3 if avail.get(s, 0)==1 else 0}:{EAN}" for s in full_order)
    return sizes, detail


# ==================== 页面解析 ====================
def _price_to_num(s: str) -> str:
    s = (s or "").replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return m.group(1) if m else "No Data"

def _sleep_jitter(base: float = 1.0):
    time.sleep(base * random.uniform(0.6, 1.4))

def _refresh_session(sess: requests.Session):
    """预热首页，刷新 cookie / anti-bot token"""
    try:
        sess.get(BASE_HOME, timeout=20)
    except Exception:
        pass

def fetch_product_html(sess: requests.Session, url: str, timeout: int = 25) -> str | None:
    """
    先 requests（带 Referer），失败/被挡再回退 UC 浏览器拿 page_source。
    附带更多日志，便于定位：打印 HTTP 状态码及重试路径。
    """
    base_headers = {
        "User-Agent": sess.headers.get("User-Agent", random.choice(UA_POOL)),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": LISTING_REFERER,
    }

    # 1) requests 直连
    try:
        r = sess.get(url, headers=base_headers, timeout=timeout)
        if r.status_code == 200 and r.text and ("<html" in r.text.lower()):
            return r.text
        print(f"  ↪ requests got status {r.status_code} for {url}")
    except Exception as e:
        print(f"  ↪ requests error: {e!r}")

    # 2) requests 再试一次（补尾斜杠）
    try:
        u2 = url if url.endswith("/") else (url + "/")
        r2 = sess.get(u2, headers=base_headers, timeout=timeout)
        if r2.status_code == 200 and r2.text and ("<html" in r2.text.lower()):
            return r2.text
        print(f"  ↪ requests(/{''}) got status {r2.status_code} for {u2}")
    except Exception as e2:
        print(f"  ↪ requests(/{''}) error: {e2!r}")

    # 3) —— 浏览器兜底（最稳，但较慢）——
    try:
        drv = _get_uc_driver(headless=True)
        try:
            drv.get(url)
            time.sleep(random.uniform(1.2, 2.2))  # 轻微抖动
            html = drv.page_source
            if html and ("<html" in html.lower()):
                print("  ↪ UC fallback succeeded")
                return html
        finally:
            try: drv.quit()
            except Exception: pass
    except Exception as e3:
        print(f"  ↪ UC fallback error: {e3!r}")

    return None



def _parse_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # 名称 & 颜色（标题）
    h1 = soup.select_one("h1.primary-title a") or soup.select_one("h1.primary-title")
    raw_title = _text(h1)

    # a > span 里常放颜色；从标题尾部去掉，避免 "Navy Navy"
    color_from_span = ""
    if h1:
        span = h1.find("span")
        if span:
            color_from_span = _text(span)
            if color_from_span:
                raw_title = re.sub(rf"\s*\b{re.escape(color_from_span)}\b\s*$", "", raw_title, flags=re.I).strip()

    # 标题 “Name - Color” 切分兜底
    name_from_split, color_from_title = _split_title_color(raw_title)

    # 最终名称
    name = name_from_split or raw_title or "No Data"
    if name == "No Data":
        og = soup.find("meta", {"property": "og:title"})
        if og and og.get("content"):
            name = og["content"].strip()

    # 最终颜色：span > 标题尾巴 > JSON-LD
    color = color_from_span or color_from_title
    jsonld = _parse_json_ld(soup)
    if not color and isinstance(jsonld, dict):
        color = (jsonld.get("color") or "").strip()

    # 再清理一次：把颜色词从名称尾部去掉（防重复）
    if color:
        name = re.sub(rf"(?:\s+\b{re.escape(color)}\b)+\s*$", "", name, flags=re.I).strip()

    # 价格：现价（Adjusted）/ 原价（Product）
    price_wrap = soup.select_one(".product__short-description .product__price") or soup.select_one(".product__price")
    adjusted_price = product_price = "No Data"
    if price_wrap:
        curr = price_wrap.select_one(".price:not(.price--compare)")
        comp = price_wrap.select_one(".price--compare")
        if curr:   adjusted_price = _price_to_num(_text(curr))
        if comp:   product_price  = _price_to_num(_text(comp))
    if (adjusted_price == "No Data" or product_price == "No Data") and isinstance(jsonld, dict):
        offers = jsonld.get("offers")
        if isinstance(offers, dict) and offers.get("price"):
            adjusted_price = _price_to_num(str(offers.get("price")))
            if product_price == "No Data":
                product_price = adjusted_price

    # 尺码 & 库存
    gender = "Men"  # 站点全为男款
    sizes, size_detail = _extract_sizes(soup, gender)



    # Feature & Description（Details 模块；再兜底 JSON-LD / meta description）
    features: list[str] = []
    for head in soup.select(".section.product__details h3"):
        if "details" in _text(head).lower():
            ul = head.find_next("ul")
            if ul:
                features = [_text(li) for li in ul.find_all("li")]
                break
    if not features:
        ul = soup.select_one(".section.product__details ul")
        if ul:
            features = [_text(li) for li in ul.find_all("li")]
    description = features[0] if features else ""
    if not description and isinstance(jsonld, dict) and jsonld.get("description"):
        description = (jsonld["description"] or "").strip()
    if not description:
        meta = soup.find("meta", {"name": "description"})
        if meta and meta.get("content"):
            description = meta["content"].strip()

    # 固定字段
    gender         = "Men"       # 站点全为男款
    product_code   = "No Data"   # 站点未提供款号/条码
    product_mat    = "No Data"   # 未提供材质
    style_category = "No Data"   # 未提供类目
    feature_join   = "; ".join(features) if features else "No Data"

        # ========== 商品编码匹配 ==========
    product_code = "No Data"
    try:
        raw_conn = get_raw_connection() 
        results = match_product(
            raw_conn,
            scraped_title=name,
            scraped_color=color,
            table=PRODUCTS_TABLE,   # 建议用统一配置表名
            name_weight=0.72,
            color_weight=0.18,
            type_weight=0.10,
            topk=5,
            recall_limit=2000,
            min_name=0.92,
            min_color=0.85,
            require_color_exact=False,
            require_type=False,
        )
        product_code = choose_best(results)
        print("🔎 match debug")
        print(f"  raw_title: {name}")
        print(f"  raw_color: {color}")
        
    except Exception as e:
        print(f"❌ 匹配失败: {e}")

    # 返回与 HOF/Very 对齐的键名
    return {
        "Product Code":        product_code,
        "Product Name":        name or "No Data",
        "Product Description": description or "No Data",
        "Product Gender":      gender,
        "Product Color":       color or "No Data",
        "Product Price":       product_price or "No Data",
        "Adjusted Price":      adjusted_price or "No Data",
        "Product Material":    product_mat,
        "Style Category":      style_category,
        "Feature":             feature_join,
        "Product Size":        ";".join(sizes) if sizes else "No Data",
        "Product Size Detail": size_detail or "No Data",
        "Source URL":          url,
        "Site Name":           SITE_NAME,
    }

def _resolve_output_path(info: dict, out_dir: Path) -> Path:
    """
    有编码 → {code}.txt
    无编码 → _UNMATCHED/<CleanTitle[_Color]>_<hash4>.txt
    """
    code = (info.get("Product Code") or "").strip()
    if code and code.lower() != "no data":
        return out_dir / f"{code}.txt"

    # —— 没匹配上：放入 _UNMATCHED 子目录，避免与已匹配混在一起
    subdir = out_dir / "_UNMATCHED"
    subdir.mkdir(parents=True, exist_ok=True)

    title = info.get("Product Name") or "No_Data"
    color = info.get("Product Color") or ""
    base  = _safe_filename(f"{title}" + (f"_{color}" if color and color != "No Data" else ""))
    # 用 Source URL + 标题 生成短哈希，降低重名风险
    suffix = _short_hash((info.get("Source URL") or "") + title)
    return subdir / f"{base}_{suffix}.txt"


# ==================== 写盘 ====================
def _write_txt(info: dict, out_dir: Path) -> Path:
    title = info.get("Product Name") or "No_Data"
    color = info.get("Product Color") or ""
    base  = _safe_filename(f"{title}" + (f"_{color}" if color and color != "No Data" else ""))
    code = info.get("Product Code") or "NoData"
    path = _resolve_output_path(info, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if write_txt is not None:
        # 使用项目内格式化写入（与其他站点完全一致）
        write_txt(info, path)
    else:
        # 轻量 fallback：使用与 HOF/Very 一致的字段顺序写入
        order = [
            "Product Code","Product Name","Product Description","Product Gender",
            "Product Color","Product Price","Adjusted Price","Product Material",
            "Style Category","Feature","Product Size","Product Size Detail",
            "Source URL","Site Name"
        ]
        with open(path, "w", encoding="utf-8") as f:
            for k in order:
                f.write(f"{k}: {info.get(k, 'No Data')}\n")

    print(f"✅ 写入: {path.name} (code={info.get('Product Code')})")
    return path

# ==================== 主流程 ====================
def terraces_fetch_info(max_count: int | None = None, timeout: int = 30) -> None:
    links_file = Path(BARBOUR["LINKS_FILES"][SUPPLIER_KEY])
    out_dir    = Path(BARBOUR["TXT_DIRS"][SUPPLIER_KEY])

    if not links_file.exists():
        print(f"❌ 未找到链接文件: {links_file}")
        return

    urls = [ln.strip() for ln in links_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    total = len(urls)
    if max_count is not None:
        urls = urls[:max_count]
    print(f"📄 共 {len(urls)} / {total} 个商品页面待解析...")

    sess = requests.Session()
    # 初始 UA + 预热首页拿 cookie
    sess.headers.update({"User-Agent": random.choice(UA_POOL)})
    _refresh_session(sess)

    ok = fail = 0
    failed_links_path = out_dir.parent / "terraces_failed.txt"
    failed = []

    for i, url in enumerate(urls, 1):
        try:
            # 每抓 40 个短暂停顿，降低触发率
            if i % 40 == 0:
                print("⏳ 节流中（短暂休息 8s）...")
                time.sleep(8)

            print(f"\n🌐 正在抓取: {url}  [{i}/{len(urls)}]")
            html = fetch_product_html(sess, url, timeout=timeout)
            if not html:
                raise requests.HTTPError("fetch_product_html returned None")

            info = _parse_page(html, url)
            _write_txt(info, out_dir)
            ok += 1

        except Exception as e:
            fail += 1
            failed.append(url)
            print(f"[失败] [{i}/{len(urls)}] ❌ {url}\n    {repr(e)}")

    if failed:
        failed_links_path.parent.mkdir(parents=True, exist_ok=True)
        failed_links_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"\n⚠️ 已将失败链接写入: {failed_links_path}")

    print(f"\n完成：成功 {ok}，失败 {fail}，输出目录：{out_dir}")


if __name__ == "__main__":
    terraces_fetch_info()
