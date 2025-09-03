# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour 商品抓取（精简版）
- 解析商品：标题、颜色、价格、尺码
- 用第三方相似度（RapidFuzz）在数据库 barbour_products 上做“标题+颜色”匹配，拿到 product_code
- TXT 文件名 = product_code.txt；如果未命中，则用安全标题命名
"""

from __future__ import annotations

import re
import os
import json
import time
import tempfile
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 第三方与解析 =====
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== DB 与项目配置 =====
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from config import BARBOUR, BRAND_CONFIG
from barbour.core.site_utils import assert_site_or_raise as canon
from barbour.core.sim_matcher import match_product, choose_best, explain_results

# ================== 站点与目录 ==================
SITE_NAME = canon("houseoffraser")
LINKS_FILE: str = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS_TABLE: str = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# ================== 可调参数 ==================
WAIT_PRICE_SECONDS = 8           # 等价面价模块的最长等待（秒）
DEFAULT_DELAY = 2.0              # 打开页面后的缓冲等待（秒）
MAX_WORKERS_DEFAULT = 4          # 并发数
MIN_SCORE = 0.72                 # 相似度阈值
MIN_LEAD = 0.04                  # 领先幅度阈值（Top1 与 Top2 差值）
NAME_WEIGHT = 0.75               # 名称权重
COLOR_WEIGHT = 0.25              # 颜色权重

# ================== 并发去重 + 原子写 ==================
_WRITTEN: set[str] = set()
_WRITTEN_LOCK = threading.Lock()

def _atomic_write_bytes(data: bytes, dst: Path, retries: int = 6, backoff: float = 0.25) -> bool:
    """
    更强健的原子写：为并发与 Windows 句柄占用做容错。
    - 唯一 tmp 文件名，避免跨线程冲突
    - PermissionError/FileExistsError 退避重试
    - 若重试后目标已存在（多线程已写入），按成功处理
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        tmp = None
        try:
            # 唯一 tmp：放在同目录，降低跨盘 replace 风险
            with tempfile.NamedTemporaryFile(
                delete=False, dir=str(dst.parent), prefix=".tmp_", suffix=f".{os.getpid()}.{threading.get_ident()}"
            ) as tf:
                tmp = Path(tf.name)
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())
            try:
                # 若目标已存在且被占用，可能抛 PermissionError；退避重试
                os.replace(tmp, dst)  # 原子替换
            finally:
                if tmp and tmp.exists():
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
            return True
        except (PermissionError, FileExistsError, OSError) as e:
            # 若目标已经存在（可能其他线程先完成），当作成功
            if dst.exists():
                return True
            # 退避后重试
            time.sleep(backoff * (i + 1))
            # 最后一轮前，尝试清理残留 tmp
            try:
                if tmp and tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            # 其他异常也做退避
            time.sleep(backoff * (i + 1))
    # 到此仍失败，但若目标已存在（并发已成功），也算成功
    return dst.exists()


def _kv_txt_bytes(info: Dict[str, Any]) -> bytes:
    fields = [
        "Product Code","Product Name","Product Description","Product Gender",
        "Product Color","Product Price","Adjusted Price","Product Material",
        "Style Category","Feature","Product Size","Product Size Detail",
        "Source URL","Site Name"
    ]
    lines = [f"{k}: {info.get(k, 'No Data')}" for k in fields]
    return ("\n".join(lines) + "\n").encode("utf-8", errors="ignore")

def _safe_name(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|'\s]+", "_", s or "NoName")

def get_dbapi_connection(conn_or_engine):
    """把 SQLAlchemy Engine/Connection 剥成 DBAPI（有 .cursor()）供 sim_matcher 使用"""
    if hasattr(conn_or_engine, "cursor"):
        return conn_or_engine
    if hasattr(conn_or_engine, "raw_connection"):
        return conn_or_engine.raw_connection()
    c = getattr(conn_or_engine, "connection", None)
    if c is not None:
        dbapi = getattr(c, "dbapi_connection", None)
        if dbapi is not None and hasattr(dbapi, "cursor"):
            return dbapi
        inner = getattr(c, "connection", None)
        if inner is not None and hasattr(inner, "cursor"):
            return inner
        if hasattr(c, "cursor"):
            return c
    return conn_or_engine

# ================== 解析函数（够用且稳） ==================
def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _extract_title(soup: BeautifulSoup) -> str:
    t = _clean(soup.title.get_text()) if soup.title else "No Data"
    # 去掉站名后缀
    t = re.sub(r"\s*\|\s*House of Fraser\s*$", "", t, flags=re.I)
    return t or "No Data"

def _extract_desc(soup: BeautifulSoup) -> str:
    m = soup.find("meta", attrs={"property": "og:description"})
    return _clean(m["content"]) if (m and m.get("content")) else "No Data"

def _extract_color(soup: BeautifulSoup) -> str:
    c = soup.select_one("#colourName")
    if c:
        name = _clean(c.get_text())
        if name:
            return name
    ul = soup.find("ul", id="ulColourImages")
    if ul:
        li = ul.find("li", attrs={"aria-checked": "true"})
        if li:
            txt = (li.get("data-text") or "").strip()
            if txt:
                return _clean(txt)
            img = li.find("img")
            if img and img.get("alt"):
                return _clean(img["alt"])
    return "No Data"

def _extract_gender(title: str, soup: BeautifulSoup) -> str:
    t = (title or "").lower()
    if "women" in t: return "女款"
    if "men" in t:   return "男款"
    if any(k in t for k in ["kids","girls","boys"]): return "童款"
    return "No Data"

def _to_num(s: Optional[str]) -> Optional[float]:
    if not s: return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s.replace(",", ""))
    return float(m.group(1)) if m else None

def _extract_prices(soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
    # 现价 / 票面价
    sp = soup.select_one("#lblSellingPrice")
    tp = soup.select_one("#lblTicketPrice")
    if sp:
        curr = _to_num(sp.get_text(" ", strip=True))
        orig = _to_num(tp.get_text(" ", strip=True)) if tp else None
        if curr is not None:
            return curr, (orig if orig is not None else curr)
    # 结构化数据兜底
    ld = soup.select_one("#structuredDataLdJson")
    if ld:
        try:
            data = json.loads(ld.get_text())
            if isinstance(data, list) and data:
                offers = (data[0] or {}).get("offers") or []
                if offers:
                    curr = _to_num(str(offers[0].get("price")))
                    if curr is not None:
                        return curr, curr
        except Exception:
            pass
    return (None, None)

def _extract_size_pairs(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    sel = soup.find("select", id="sizeDdl")
    results: List[Tuple[str, str]] = []
    if not sel: return results
    for opt in sel.find_all("option"):
        txt = _clean(opt.get_text())
        if not txt or txt.lower().startswith("select"): continue
        cls = opt.get("class") or []
        title = _clean(opt.get("title") or "")
        oos = ("greyOut" in cls) or ("out of stock" in title.lower())
        status = "无货" if oos else "有货"
        norm = re.sub(r"\s*\(.*?\)\s*", "", txt).strip()
        norm = re.sub(r"^(UK|EU|US)\s+", "", norm, flags=re.I)
        results.append((norm, status))
    return results

def _build_size_lines(pairs: List[Tuple[str, str]]) -> Tuple[str, str]:
    by_size: Dict[str, str] = {}
    for size, status in pairs:
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            by_size[size] = status
    def _key(k: str):
        m = re.fullmatch(r"\d{1,3}", k)
        return (0, int(k)) if m else (1, k)
    ordered = sorted(by_size.keys(), key=_key)
    ps = ";".join(f"{k}:{by_size[k]}" for k in ordered) or "No Data"
    EAN = "0000000000000"
    psd = ";".join(f"{k}:{3 if by_size[k]=='有货' else 0}:{EAN}" for k in ordered) or "No Data"
    return ps, psd

def parse_info(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    desc  = _extract_desc(soup)
    color = _extract_color(soup)
    gender = _extract_gender(title, soup)
    curr, orig = _extract_prices(soup)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr

    size_pairs = _extract_size_pairs(soup)
    product_size, product_size_detail = _build_size_lines(size_pairs)

    info = {
        "Product Code": "No Data",
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color or "No Data",
        "Product Price": f"{orig:.2f}" if orig else "No Data",
        "Adjusted Price": f"{curr:.2f}" if curr else "No Data",
        "Product Material": "No Data",
        "Style Category": "casual wear",
        "Feature": "No Data",
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Source URL": url,
        "Site Name": SITE_NAME,
    }
    return info

# ================== Selenium & 抓取流程 ==================
def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return uc.Chrome(options=options)

def process_url(url: str, conn: Connection, delay: float = DEFAULT_DELAY, headless: bool = False) -> Path:
    print(f"\n🌐 正在抓取: {url}")
    driver = get_driver(headless=headless)
    try:
        driver.get(url)
        if WAIT_PRICE_SECONDS > 0:
            try:
                WebDriverWait(driver, WAIT_PRICE_SECONDS).until(
                    EC.presence_of_element_located((By.ID, "lblSellingPrice"))
                )
            except Exception:
                pass
        if delay > 0:
            time.sleep(delay)
        html = driver.page_source
    finally:
        try: driver.quit()
        except Exception: pass

    info = parse_info(html, url)

    # ============= 第三方相似度匹配（不依赖 keyword 字段） =============
    raw_conn = get_dbapi_connection(conn)
    title = info.get("Product Name") or ""
    color = info.get("Product Color") or ""

    results = match_product(
        raw_conn,
        scraped_title=title,
        scraped_color=color,
        table=PRODUCTS_TABLE,
        name_weight=0.72,
        color_weight=0.18,
        type_weight=0.10,
        topk=5,
        recall_limit=2000,
        # ↓ 新增：名称/颜色硬门槛（严格）
        min_name=0.92,
        min_color=0.85,
        # 选配：只接受颜色“等值/同义”
        require_color_exact=False,   # 设 True 更严
        # 选配：要求类型一致（jacket/gilet/coat 等）
        require_type=False,
    )
    code = choose_best(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
    if not code and results:
        st = results[0].get("type_scraped")
        if st:
            for r in results:
                if r.get("type_db") == st:
                    code = r["product_code"]
                    print(f"🎯 tie-break by type → {code}")
                    break

    print("🔎 match debug")
    print(f"  raw_title: {title}")
    print(f"  raw_color: {color}")
    if results:
        print(f"  cleaned : {results[0]['title_clean']}  | color_norm: {results[0].get('style_clean','') and results[0]['title_clean'].split(' ')[-1] if False else (results[0]['color_score']>=0)}")
    txt, why = explain_results(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
    print(txt)
    if code:
        print(f"  ⇒ ✅ choose_best = {code}")
    else:
        print(f"  ⇒ ❌ no match ({why})")

    if not code and results:
        # 记录一下前三，方便你在控制台观察；无需任何调试文件
        print("🧪 top:", " | ".join(f"{r['product_code']}[{r['score']:.3f}]" for r in results[:3]))

    # 命名：优先用编码
    if code:
        info["Product Code"] = code
        out_name = f"{code}.txt"
    else:
        # 为避免不同页面同标题造成同名（并发写冲突），追加 URL 短哈希
        short = f"{abs(hash(url)) & 0xFFFF:04x}"
        out_name = f"{_safe_name(title)}_{short}.txt"

    out_path = TXT_DIR / out_name
    
    # 并发去重
    with _WRITTEN_LOCK:
        if out_name in _WRITTEN:
            print(f"↩️  跳过重复写入：{out_name}")
            return out_path
        _WRITTEN.add(out_name)

    # 原子写入
    payload = _kv_txt_bytes(info)
    ok = _atomic_write_bytes(payload, out_path)
    if ok:
        print(f"✅ 写入: {out_path.name} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")
    return out_path

def houseoffraser_fetch_info(max_workers: int = MAX_WORKERS_DEFAULT, delay: float = DEFAULT_DELAY, headless: bool = False):
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return

    urls = [line.strip() for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")]
    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0:
        return

    engine_url = f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['dbname']}"
    engine = create_engine(engine_url)

    indexed = list(enumerate(urls, start=1))

    def _worker(idx_url):
        idx, u = idx_url
        print(f"[启动] [{idx}/{total}] {u}")
        try:
            with engine.begin() as conn:
                path = process_url(u, conn=conn, delay=delay, headless=headless)
            return (idx, u, str(path), None)
        except Exception as e:
            return (idx, u, None, e)

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hof") as ex:
        futures = [ex.submit(_worker, iu) for iu in indexed]
        for fut in as_completed(futures):
            idx, u, path, err = fut.result()
            if err is None:
                ok += 1
                print(f"[完成] [{idx}/{total}] ✅ {u} -> {path}")
            else:
                fail += 1
                print(f"[失败] [{idx}/{total}] ❌ {u}\n    {repr(err)}")

    print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")

if __name__ == "__main__":
    houseoffraser_fetch_info()
