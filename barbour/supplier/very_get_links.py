# -*- coding: utf-8 -*-
"""
barbour/supplier/very_get_links.py —— 覆盖版（并集解析 + 强滚动 + 规范翻页）
- 标准 Selenium + 有头 Chrome（稳定、贴近真人）
- 自动翻页：始终强制携带 ?numProducts=96
- 三重解析并集：JSON-LD → DOM → 正则（不再谁命中就提前返回）
- 写入：config.BARBOUR["LINKS_FILES"]["very"]
- Debug：每页保存 html/txt/json，记录各方法数量
"""

from __future__ import annotations
import re, json, time, urllib.parse as up
from pathlib import Path
from typing import List, Set, Optional, Any

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from config import BARBOUR

# ===== 站点与输出 =====
BASE = "https://www.very.co.uk"
LIST_START_URL = "https://www.very.co.uk/promo/barbour-barbour-international?numProducts=96"

OUTPUT_FILE: Path = BARBOUR["LINKS_FILES"]["very"]
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
DEBUG_DIR: Path = OUTPUT_FILE.parent / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ===== 运行参数 =====
WAIT_EACH = 3.0          # 每页加载等待
SCROLL_PAUSE = 0.6       # 滚动后等待
MAX_PAGES = 50           # 安全上限
NUM_PER_PAGE = 96
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

# ===== 小工具 =====
def _ts() -> str:
    import time as _t
    return _t.strftime("%Y%m%d-%H%M%S")

def _absolutize(url: str) -> str:
    return up.urljoin(BASE, url)

def _write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8", errors="ignore")

def _write_json(path: Path, data: Any):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _save_debug(page_index: int, html: str, links: List[str], method_used: str, note: str = ""):
    prefix = DEBUG_DIR / f"page-{page_index:02d}-{_ts()}"
    _write_text(prefix.with_suffix(".html"), html or "")
    _write_text(prefix.with_suffix(".txt"), "\n".join(links))
    _write_json(prefix.with_suffix(".json"), {
        "page_index": page_index,
        "method_used": method_used,
        "links_count": len(links),
        "note": note
    })

def _ensure_num_products(u: str) -> str:
    """确保 URL 上携带 numProducts=96。"""
    pr = urlparse(u)
    qs = dict(parse_qsl(pr.query, keep_blank_values=True))
    if str(qs.get("numProducts", "")) != str(NUM_PER_PAGE):
        qs["numProducts"] = str(NUM_PER_PAGE)
    pr = pr._replace(query=urlencode(qs, doseq=True))
    return urlunparse(pr)

# ===== 浏览器构造 =====
def _build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument(f"--user-agent={UA}")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    # 如有兼容性问题，可启用：
    # opts.add_argument("--remote-allow-origins=*")
    return webdriver.Chrome(options=opts)

# ===== 交互动作 =====
def _accept_cookies(driver):
    try:
        btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        btn.click()
        time.sleep(0.8)
        return True
    except Exception:
        pass
    try:
        for sel in ["button", "[role='button']"]:
            for e in driver.find_elements(By.CSS_SELECTOR, sel):
                txt = (e.text or "").strip().lower()
                if any(k in txt for k in ["accept", "agree", "got it", "allow"]):
                    e.click()
                    time.sleep(0.8)
                    return True
    except Exception:
        pass
    return False

def _human_like_scroll(driver):
    """多段滚动触发懒加载（比旧版更充分）。"""
    try:
        h = driver.execute_script("return document.body.scrollHeight") or 2000
        steps = [0.25, 0.5, 0.75, 1.0]
        for s in steps:
            driver.execute_script(f"window.scrollTo(0, {int(h*s)});")
            time.sleep(SCROLL_PAUSE)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE)
    except Exception:
        pass

# ===== 解析 =====
def _parse_jsonld_products(soup: BeautifulSoup) -> List[str]:
    out: List[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            raw2 = re.sub(r",\s*([}\]])", r"\1", raw)  # 宽松去尾逗号
            try:
                data = json.loads(raw2)
            except Exception:
                continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "ProductCollection":
                inc = node.get("includesObject") or []
                for x in inc:
                    url = (((x or {}).get("typeOfGood") or {}).get("url") or "").strip()
                    if url.endswith(".prd"):
                        out.append(_absolutize(url))
    return out

def _parse_dom_products(soup: BeautifulSoup) -> List[str]:
    links: Set[str] = set()
    # 1) 常规
    for a in soup.select("a[href$='.prd']"):
        href = a.get("href") or ""
        if href:
            links.add(_absolutize(href))
    # 2) 更宽的匹配（有些写成 ...something.prd?param=...）
    for a in soup.select("a[href*='.prd']"):
        href = a.get("href") or ""
        if href.endswith(".prd"):
            links.add(_absolutize(href))
    # 3) data-product-url 兜底
    for e in soup.select("[data-product-url]"):
        href = e.get("data-product-url") or ""
        if href.endswith(".prd"):
            links.add(_absolutize(href))
    return list(links)

# 4) 正则兜底: "/something/160XXXXXXXXX.prd"
_PRD_RE = re.compile(r'"/[a-z0-9\-]+/\d{10}\.prd"', re.I)
def _regex_fallback(html: str) -> List[str]:
    found = set()
    for m in _PRD_RE.finditer(html or ""):
        rel = m.group(0).strip('"')
        found.add(_absolutize(rel))
    return sorted(found)

def _find_next_url(soup: BeautifulSoup) -> Optional[str]:
    ln = soup.find("link", attrs={"rel": "next"})
    if ln and ln.get("href"):
        return _ensure_num_products(_absolutize(ln["href"]))
    for a in soup.select("a[rel='next'], a[href*='?page=']"):
        href = a.get("href") or ""
        if "page=" in href:
            return _ensure_num_products(_absolutize(href))
    return None

# ===== 主流程 =====
def fetch_listing_urls(start_url: str = LIST_START_URL) -> List[str]:
    start_url = _ensure_num_products(start_url)  # 保底确保页大小
    driver = _build_driver()
    all_links: Set[str] = set()
    seen_pages: Set[str] = set()

    try:
        url = start_url
        page_no = 1
        while url and len(seen_pages) < MAX_PAGES:
            if url in seen_pages:
                break
            seen_pages.add(url)

            print(f"🌐 打开列表页: {url}")
            driver.get(url)
            time.sleep(WAIT_EACH)
            _accept_cookies(driver)
            _human_like_scroll(driver)
            time.sleep(WAIT_EACH)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # 同页三种方式“并集”
            links_jsonld = _parse_jsonld_products(soup)
            links_dom    = _parse_dom_products(soup)
            links_regex  = _regex_fallback(html)

            links_set = set(links_jsonld) | set(links_dom) | set(links_regex)
            links = sorted(links_set)

            counts = {
                "jsonld": len(set(links_jsonld)),
                "dom":    len(set(links_dom)),
                "regex":  len(set(links_regex))
            }
            method = max(counts, key=counts.get)

            print(f"  - 解析到 {len(links)} 个商品链接（jsonld={counts['jsonld']}, dom={counts['dom']}, regex={counts['regex']} → 主方法:{method}）")
            _save_debug(page_no, html, links,
                        method_used=f"{method} (jsonld={counts['jsonld']}, dom={counts['dom']}, regex={counts['regex']})",
                        note=f"url={url}")

            for lk in links:
                all_links.add(lk)
            print(f"    累计去重后：{len(all_links)}")

            nxt = _find_next_url(soup)
            if nxt and nxt not in seen_pages:
                page_no += 1
                url = nxt
            else:
                break

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return sorted(all_links)

def save_to_file(urls: List[str], path: Path):
    payload = "\n".join(urls) + ("\n" if urls else "")
    path.write_text(payload, encoding="utf-8")
    print(f"✅ 已写入 {len(urls)} 条链接 → {path}")

def very_get_links(list_start_url: str = LIST_START_URL):
    urls = fetch_listing_urls(list_start_url)
    save_to_file(urls, OUTPUT_FILE)

if __name__ == "__main__":
    very_get_links()
