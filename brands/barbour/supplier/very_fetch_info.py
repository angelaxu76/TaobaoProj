# -*- coding: utf-8 -*-
"""
Very | Barbour 商品抓取（与 houseoffraser_fetch_info 结构对齐）
- 解析：标题、描述、颜色、原价、折扣价、尺码库存（有货/无货）→ TXT
- 相似度匹配 barbour_products（标题+颜色），命中则用编码命名 TXT
- 支持并发与原子写入；字段/格式与 HOF 版一致
"""

from __future__ import annotations

import os
import json
import time
import tempfile
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 第三方与解析 =====
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 统一 Selenium 驱动
from common_taobao.core.selenium_utils import get_driver as selenium_get_driver, quit_driver

# ===== DB 与项目配置 =====
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from config import BARBOUR, BRAND_CONFIG
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from brands.barbour.core.sim_matcher import match_product, choose_best, explain_results

import re  # safe filename 等用到

# ================== 站点与目录 ==================
SITE_NAME = canon("very")
LINKS_FILE: str = BARBOUR["LINKS_FILES"]["very"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["very"]
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

# ===== 标准尺码表（用于补齐未出现尺码=0） =====
WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（不含52）

def _full_order_for_gender(gender: str) -> list[str]:
    """根据性别返回完整尺码顺序；未知/童款先按男款处理。"""
    g = (gender or "").lower()
    if "女" in g or "women" in g or "ladies" in g:
        return WOMEN_ORDER
    return MEN_ALPHA_ORDER + MEN_NUM_ORDER


# ================== 并发去重 + 原子写 ==================
_WRITTEN: set[str] = set()
_WRITTEN_LOCK = threading.Lock()

def _atomic_write_bytes(data: bytes, dst: Path, retries: int = 6, backoff: float = 0.25) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, dir=str(dst.parent), prefix=".tmp_", suffix=f".{os.getpid()}.{threading.get_ident()}"
            ) as tf:
                tmp = Path(tf.name)
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())
            try:
                os.replace(tmp, dst)
            finally:
                if tmp and tmp.exists():
                    try: tmp.unlink(missing_ok=True)
                    except Exception: pass
            return True
        except (PermissionError, FileExistsError, OSError):
            if dst.exists():
                return True
            time.sleep(backoff * (i + 1))
            try:
                if tmp and tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            time.sleep(backoff * (i + 1))
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

# ================== 工具函数 ==================

def _choose_full_order_for_gender(gender: str, present: set[str]) -> list[str]:
    """男款在【字母系(2XS–3XL)】与【数字系(30–50,不含52)】二选一；女款固定 4–20。"""
    g = (gender or "").lower()
    if "女" in g or "women" in g or "ladies" in g:
        return WOMEN_ORDER[:]  # 女款固定 4..20

    has_num   = any(k in MEN_NUM_ORDER   for k in present)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in present)
    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]          # 只用数字系 30..50
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]        # 只用字母系 2XS..3XL
    if has_num or has_alpha:
        num_count   = sum(1 for k in present if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in present if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]
    # 实在判不出来：默认用字母系（外套更常见）
    return MEN_ALPHA_ORDER[:]


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _json_from_script(html: str, var_name: str) -> Optional[dict]:
    """
    从 window.__product_body_initial_state__= {...}; 抽 JSON
    """
    pat = re.compile(rf"{re.escape(var_name)}\s*=\s*({{.*?}})\s*;", re.S)
    m = pat.search(html)
    if not m:
        return None
    blob = m.group(1)
    try:
        return json.loads(blob)
    except Exception:
        try:
            blob2 = re.sub(r",\s*([}\]])", r"\1", blob)
            return json.loads(blob2)
        except Exception:
            return None

def _extract_title(soup: BeautifulSoup, initial: Optional[dict]) -> str:
    if initial and initial.get("name"):
        return _clean(initial["name"])
    t = _clean(soup.title.get_text()) if soup.title else "No Data"
    t = re.sub(r"\s*\|\s*Very\s*$", "", t, flags=re.I)
    return t or "No Data"

def _extract_desc(soup: BeautifulSoup, productData: Optional[dict]) -> str:
    m = soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"):
        return _clean(m["content"])
    if productData and productData.get("description"):
        return _clean(productData["description"])
    return "No Data"

def _extract_color(initial: Optional[dict]) -> str:
    if initial and isinstance(initial.get("skus"), list):
        for sku in initial["skus"]:
            opts = sku.get("options") or {}
            col = opts.get("colour")
            if col:
                return _clean(str(col))
    return "No Data"

def _extract_gender(title: str, soup: BeautifulSoup, productData: Optional[dict]) -> str:
    t = (title or "").lower()
    if "women" in t or "ladies" in t: return "女款"
    if "men" in t: return "男款"
    if productData:
        dept = (productData.get("subcategory") or "") + " " + (productData.get("category") or "") + " " + (productData.get("department") or "")
        d = dept.lower()
        if any(k in d for k in ["ladies","women","women's"]): return "女款"
        if "men" in d: return "男款"
    return "No Data"

def _to_num(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", str(s).replace(",", ""))
    return float(m.group(1)) if m else None

def _extract_prices(initial: Optional[dict], soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
    """
    返回 (curr, orig) -> (折后价, 原价)
    Very 的 initial_state.price.amount.decimal/previous
    """
    if initial:
        price = (initial.get("price") or {}).get("amount") or {}
        curr = _to_num(price.get("decimal") or price.get("current"))
        orig = _to_num(price.get("previous")) or curr
        if curr is not None:
            return curr, (orig if orig is not None else curr)
    m_curr = soup.find("meta", attrs={"property": "product:price:amount"})
    if m_curr and m_curr.get("content"):
        curr = _to_num(m_curr["content"])
        return curr, curr
    return (None, None)

def _extract_sizes_and_stock(initial: Optional[dict], soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """
    返回 [(size, 有货/无货), ...]
    优先用 skus[].stock.code；失败再看 DOM 里的 checkbox disabled
    """
    pairs: List[Tuple[str, str]] = []

    # 1) JSON 优先
    if initial and isinstance(initial.get("skus"), list):
        for sku in initial["skus"]:
            opts = sku.get("options") or {}
            size = _clean(str(opts.get("size") or ""))
            if not size:
                continue
            stock = (sku.get("stock") or {}).get("code") or ""
            status = "无货"
            if stock:
                status = "有货" if stock.upper() in {"DCSTOCK", "IN_STOCK", "AVAILABLE"} else "无货"
            pairs.append((size, status))

    # 2) DOM 回退
    if not pairs:
        for inp in soup.select('input[id^="size-"][type="checkbox"]'):
            size = _clean((inp.get("id") or "").replace("size-", ""))
            if not size:
                continue
            disabled = inp.has_attr("disabled") or inp.get("aria-disabled") == "true"
            status = "无货" if disabled else "有货"
            pairs.append((size, status))

    # 尺码规范化
    _alpha_canon = {
        "XXXS":"2XS","2XS":"2XS","XXS":"XS","XS":"XS",
        "S":"S","SMALL":"S","M":"M","MEDIUM":"M","L":"L","LARGE":"L",
        "XL":"XL","X-LARGE":"XL","XXL":"2XL","2XL":"2XL","XXXL":"3XL","3XL":"3XL",
    }
    normed: List[Tuple[str, str]] = []
    for s, st in pairs:
        s2 = re.sub(r"\s*\(.*?\)\s*", "", s).strip()
        s2 = re.sub(r"^(UK|EU|US)\s+", "", s2, flags=re.I)
        s2u = s2.upper().replace("-", "").strip()
        if s2u in _alpha_canon:
            s2 = _alpha_canon[s2u]
        normed.append((s2, st))
    return normed


def _build_size_lines(pairs: List[Tuple[str, str]], gender: str) -> Tuple[str, str]:
    """
    将出现的尺码按“有货优先”合并，并补齐未出现的尺码为 无货/0。
    - Product Size:         34:有货;36:无货;...
    - Product Size Detail:  34:3:000...;36:0:000...;...
    ✅ 男款：二选一（字母系 或 数字系），绝不混用
    ✅ 女款：固定 4–20
    """
    by_size: Dict[str, str] = {}

    for size, status in (pairs or []):
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            by_size[size] = status

    present_keys = set(by_size.keys())
    full_order = _choose_full_order_for_gender(gender, present_keys)

    for k in list(by_size.keys()):
        if k not in full_order:
            by_size.pop(k, None)

    for s in full_order:
        if s not in by_size:
            by_size[s] = "无货"

    EAN = "0000000000000"
    ordered = list(full_order)
    ps  = ";".join(f"{k}:{by_size[k]}" for k in ordered) or "No Data"
    psd = ";".join(f"{k}:{3 if by_size[k]=='有货' else 0}:{EAN}" for k in ordered) or "No Data"
    return ps, psd


def _guess_material(desc: str) -> str:
    if not desc or desc == "No Data":
        return "No Data"
    m = re.search(r"Material\s*Content\s*:\s*(.+?)(?:$|Washing|Wash|Care)", desc, flags=re.I)
    if m:
        return _clean(m.group(1))
    return "No Data"


def _split_title_color(title: str) -> tuple[str, str | None]:
    t = (title or "").strip()
    if not t:
        return "No Data", None
    parts = [p.strip() for p in re.split(r"\s*-\s*", t) if p.strip()]
    if len(parts) >= 2:
        raw_color = parts[-1]
        color = re.split(r"[\/&]", re.sub(r"[^\w\s/&-]", "", raw_color))[0].strip()
        color = color.title() if color else None
        clean_title = " - ".join(parts[:-1])
        return (clean_title or t, color or None)
    return t, None


def parse_info(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    initial = _json_from_script(html, "window.__product_body_initial_state__")
    productData = None  # 暂不强依赖 mergeIntoDataLayer

    title = _extract_title(soup, initial)
    desc  = _extract_desc(soup, productData)
    color = _extract_color(initial)

    t2, color_from_title = _split_title_color(title)
    if not color or color.lower() == "no data":
        color = color_from_title or "No Data"
    title = t2

    gender = _extract_gender(title, soup, productData)
    curr, orig = _extract_prices(initial, soup)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr

    size_pairs = _extract_sizes_and_stock(initial, soup)
    product_size, product_size_detail = _build_size_lines(size_pairs, gender)

    material = _guess_material(desc)

    info = {
        "Product Code": "No Data",
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color or "No Data",
        "Product Price": f"{orig:.2f}" if orig else "No Data",
        "Adjusted Price": f"{curr:.2f}" if curr else "No Data",
        "Product Material": material,
        "Style Category": "casual wear",
        "Feature": "No Data",
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Source URL": url,
        "Site Name": SITE_NAME,
    }
    return info


# ================== Selenium 抓取单页 ==================

def process_url(url: str, conn: Connection, delay: float = DEFAULT_DELAY, driver=None) -> Path:
    """
    单个商品页面抓取 + 解析 + 写 TXT。
    注意：driver 必须由外部创建并传入（统一由线程 worker 管理关闭）。
    """
    if driver is None:
        raise ValueError("process_url 现在要求显式传入 driver，请从 selenium_utils.get_driver 创建。")

    print(f"\n🌐 正在抓取: {url}")
    driver.get(url)
    if WAIT_PRICE_SECONDS > 0:
        try:
            WebDriverWait(driver, WAIT_PRICE_SECONDS).until(
                EC.presence_of_element_located((By.TAG_NAME, "title"))
            )
        except Exception:
            pass
    if delay > 0:
        time.sleep(delay)
    html = driver.page_source

    info = parse_info(html, url)

    # ============= 相似度匹配（与 HOF 一致） =============
    raw_conn = get_dbapi_connection(conn)
    title = info.get("Product Name") or ""
    color = info.get("Product Color") or ""

    print("title:::::::::::::" + title)
    print("color:::::::::::::" + color)

    results = match_product(
        raw_conn,
        scraped_title=title,
        scraped_color=color,
        table=PRODUCTS_TABLE,
        name_weight=0.72,
        color_weight=0.18,
        type_weight=0.10,
        topk=20,
        recall_limit=5000,
        min_name=None,
        min_color=None,
        require_color_exact=False,
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
    txt, why = explain_results(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
    print(txt)
    if code:
        print(f"  ⇒ ✅ choose_best = {code}")
    else:
        print(f"  ⇒ ❌ no match ({why})")
        if results:
            print("🧪 top:", " | ".join(f"{r['product_code']}[{r['score']:.3f}]" for r in results[:3]))

    # 命名：优先用编码
    if code:
        info["Product Code"] = code
        out_name = f"{code}.txt"
    else:
        short = f"{abs(hash(url)) & 0xFFFF:04x}"
        out_name = f"{_safe_name(title)}_{short}.txt"

    out_path = TXT_DIR / out_name

    # 并发去重
    with _WRITTEN_LOCK:
        if out_name in _WRITTEN:
            print(f"↩️  跳过重复写入：{out_name}")
            return out_path
        _WRITTEN.add(out_name)

    payload = _kv_txt_bytes(info)
    ok = _atomic_write_bytes(payload, out_path)
    if ok:
        print(f"✅ 写入: {out_path.name} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")
    return out_path


# ================== 多线程封装（统一框架） ==================

def _process_single_url(idx: int, total: int, url: str, engine, delay: float, headless: bool):
    """
    单 URL 的线程任务：
      - 为该任务创建一个专用 driver（selenium_utils）
      - 打开 DB 事务，调用 process_url
      - 关闭 driver
    返回: (idx, url, path_str | None, error | None)
    """
    driver_name = f"very_{idx}"
    driver = None
    try:
        driver = selenium_get_driver(
            name=driver_name,
            headless=headless,
            window_size="1200,2000",
        )
        print(f"[启动] [{idx}/{total}] {url}")
        with engine.begin() as conn:
            path = process_url(url, conn=conn, delay=delay, driver=driver)
        return idx, url, str(path), None
    except Exception as e:
        print(f"[失败] [{idx}/{total}] ❌ {url}\n    {repr(e)}")
        return idx, url, None, e
    finally:
        if driver is not None:
            try:
                quit_driver(driver_name)
            except Exception:
                pass


def very_fetch_info(max_workers: int = MAX_WORKERS_DEFAULT, delay: float = DEFAULT_DELAY, headless: bool = False):
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return

    urls = [
        line.strip()
        for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0:
        return

    engine_url = (
        f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
        f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
    )
    engine = create_engine(engine_url)

    ok, fail = 0, 0
    indexed = list(enumerate(urls, start=1))

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="very") as ex:
        futures = [
            ex.submit(_process_single_url, idx, total, url, engine, delay, headless)
            for idx, url in indexed
        ]
        for fut in as_completed(futures):
            idx, url, path, err = fut.result()
            if err is None:
                ok += 1
                print(f"[完成] [{idx}/{total}] ✅ {url} -> {path}")
            else:
                fail += 1
                print(f"[失败] [{idx}/{total}] ❌ {url}\n    {repr(err)}")

    print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")


if __name__ == "__main__":
    very_fetch_info()
