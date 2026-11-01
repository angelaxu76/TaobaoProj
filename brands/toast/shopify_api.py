# -*- coding: utf-8 -*-
"""
TOAST (https://www.toa.st) 是 Shopify 站点，直接走公开 JSON 接口，无需 Selenium：
- /collections/{handle}/products.json?limit=250&page=N   类目商品列表（带 tags / variants / images）
- /products/{handle}.js                                   单品详情（带 available / barcode / 价格单位为便士）

本文件只放 collect / fetch / download 三个脚本共用的请求与编码工具。

请求方式（TOAST["FETCH_MODE"]）：
- "browser"（默认）：弹出真实 Chrome，先打开首页拿到 Cloudflare / Shopify cookie，之后所有接口都在页面内用 fetch() 请求。
  python requests 会被识别成机器人直接 429，浏览器不会。
- "requests"：直接用 requests 请求（旧方式）。
"""
from __future__ import annotations

import atexit
import random
import re
import threading
import time
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlparse

import requests
from requests.structures import CaseInsensitiveDict

from config import TOAST

SITE_ROOT = TOAST.get("SITE_ROOT", "https://www.toa.st")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# 站点前面有 Cloudflare：短时间请求太密会对整个 IP 返回 429 + 人机验证页（连 .js / products.json 一起封）。
# 所以所有请求（跨线程）共用一个节流器，两次请求之间至少间隔 MIN_INTERVAL 秒。
MIN_INTERVAL = float(TOAST.get("REQUEST_MIN_INTERVAL", 1.5))
# 命中 Cloudflare 拦截后的退避时间（秒），逐次加长
CF_BACKOFF = [60, 120, 240]

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = _last_request_at + MIN_INTERVAL + random.uniform(0, 0.5) - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.time()


# ================= 浏览器请求 =================
FETCH_MODE = TOAST.get("FETCH_MODE", "browser")

_driver = None
_driver_lock = threading.RLock()

# 在页面内发 fetch，带上浏览器自己的 cookie / 指纹；结果回传给 Python
_FETCH_JS = """
const url = arguments[0], done = arguments[arguments.length - 1];
fetch(url, {credentials: "include", headers: {"Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}})
  .then(r => r.text().then(t => done({
      status: r.status,
      headers: {"Retry-After": r.headers.get("retry-after"), "Cf-Mitigated": r.headers.get("cf-mitigated")},
      text: t,
  })))
  .catch(e => done({status: 0, headers: {}, text: "", error: String(e)}));
"""


class _BrowserResponse:
    """模拟 requests.Response 的最小接口，_get 的重试 / 限流逻辑两种模式共用"""

    def __init__(self, url: str, data: dict):
        self.url = url
        self.status_code = int(data.get("status") or 0)
        self.headers = CaseInsensitiveDict({k: v for k, v in (data.get("headers") or {}).items() if v})
        self.text = data.get("text") or ""
        self.error = data.get("error")

    def json(self):
        import json
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code == 0:
            raise requests.ConnectionError(f"浏览器 fetch 失败: {self.error} ({self.url})")
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error for url: {self.url}")


def _wait_page_ready(driver, max_wait: int = 120) -> None:
    """等首页加载完；遇到 Cloudflare 验证页时等它自动通过（必要时在弹出的浏览器里手动点一下）"""
    deadline = time.time() + max_wait
    hinted = False
    while time.time() < deadline:
        try:
            title = (driver.title or "").lower()
            ready = driver.execute_script("return document.readyState") == "complete"
        except Exception:
            title, ready = "", False
        if ready and "just a moment" not in title and "verif" not in title:
            return
        if not hinted:
            print("⏳ 等待浏览器通过 Cloudflare 验证（如有人机验证请在弹出的浏览器里手动完成）...")
            hinted = True
        time.sleep(2)
    print("⚠️ 首页等待超时，继续尝试请求")


def _get_driver():
    global _driver
    with _driver_lock:
        if _driver is None:
            from common.browser.driver_auto import build_uc_driver
            print("🌐 启动浏览器（真实 Chrome 访问 TOAST）...")
            _driver = build_uc_driver(headless=False, verbose=False)
            _driver.get(SITE_ROOT)
            _wait_page_ready(_driver)
        return _driver


def refresh_browser() -> None:
    """被拦截后重新打开首页，让浏览器重新拿 cookie / 通过验证"""
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.get(SITE_ROOT)
                _wait_page_ready(_driver)
            except Exception:
                close_browser()


def close_browser() -> None:
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.quit()
            except Exception:
                pass
            # uc.Chrome.__del__ 在 Windows 上会对已关闭的进程再 quit 一次，报 OSError: 句柄无效（无害），这里屏蔽掉
            type(_driver).__del__ = lambda self: None
            _driver = None


atexit.register(close_browser)


def _request(url: str, params: Optional[dict], timeout: int):
    if FETCH_MODE != "browser":
        return requests.get(url, params=params, headers=HEADERS, timeout=timeout)

    full_url = f"{url}?{urlencode(params)}" if params else url
    with _driver_lock:
        driver = _get_driver()
        try:
            driver.set_script_timeout(timeout)
            data = driver.execute_async_script(_FETCH_JS, full_url)
        except Exception:
            # 浏览器崩溃 / 被关掉：丢弃实例，下次重试时重新启动
            close_browser()
            raise
    return _BrowserResponse(full_url, data or {})


def _is_cf_block(r) -> bool:
    return r.status_code in (403, 429) and (
        r.headers.get("Cf-Mitigated") == "challenge" or "Verifying your connection" in r.text[:3000]
    )


def _get(url: str, params: Optional[dict] = None, retry: int = 3, timeout: int = 30):
    last_err = None
    cf_hits = 0
    attempt = 0
    while attempt < retry:
        attempt += 1
        _throttle()
        try:
            r = _request(url, params, timeout)
            if _is_cf_block(r):
                if cf_hits >= len(CF_BACKOFF):
                    raise RuntimeError("Cloudflare 持续拦截（IP 被限流），请稍后再跑或降低并发")
                wait = CF_BACKOFF[cf_hits]
                cf_hits += 1
                attempt -= 1  # 被 CF 拦截不计入普通重试次数
                print(f"🛑 Cloudflare 拦截，{wait}s 后重试：{url}")
                time.sleep(wait)
                if FETCH_MODE == "browser":
                    refresh_browser()
                continue
            if r.status_code == 429:
                # Shopify 限流（JSON: TOO_MANY_REQUESTS + retry-after），整站封 IP，短间隔重试只会越封越久
                if cf_hits >= len(CF_BACKOFF):
                    raise RuntimeError("Shopify 持续限流 429（IP 被限流），请稍后再跑或调大 REQUEST_MIN_INTERVAL")
                try:
                    retry_after = int(r.headers.get("Retry-After", 0))
                except ValueError:
                    retry_after = 0
                wait = max(retry_after, CF_BACKOFF[cf_hits])
                cf_hits += 1
                attempt -= 1  # 限流不计入普通重试次数
                print(f"🛑 429 限流（retry-after={retry_after}s），{wait}s 后重试：{url}")
                time.sleep(wait)
                if FETCH_MODE == "browser":
                    refresh_browser()
                continue
            r.raise_for_status()
            return r
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"GET {url} 失败: {last_err}")


def get_json(url: str, params: Optional[dict] = None, retry: int = 3, timeout: int = 30):
    return _get(url, params=params, retry=retry, timeout=timeout).json()


def get_html(url: str, retry: int = 3, timeout: int = 30) -> str:
    return _get(url, retry=retry, timeout=timeout).text


def iter_collection_products(collection: str, page_size: int = 250, max_pages: int = 50) -> List[dict]:
    """按页拉取某个 collection 的全部商品（products.json 返回空列表即结束）"""
    products: List[dict] = []
    for page in range(1, max_pages + 1):
        data = get_json(
            f"{SITE_ROOT}/collections/{collection}/products.json",
            params={"limit": page_size, "page": page},
        )
        batch = data.get("products") or []
        if not batch:
            break
        products.extend(batch)
    return products


def product_url(handle: str) -> str:
    return f"{SITE_ROOT}/products/{handle}"


def handle_from_url(url: str) -> str:
    path = urlparse(url.strip()).path.rstrip("/")
    m = re.search(r"/products/([^/?#]+)", path)
    if not m:
        raise ValueError(f"不是 TOAST 商品链接: {url}")
    return m.group(1)


def fetch_product_js(url_or_handle: str) -> dict:
    handle = handle_from_url(url_or_handle) if "/" in url_or_handle else url_or_handle
    return get_json(f"{SITE_ROOT}/products/{handle}.js")


def tag_value(tags: List[str], key: str) -> str:
    """tags 形如 'style_colour: WTRVS27ECRU' / 'gender: Women'"""
    prefix = key.lower() + ":"
    for t in tags or []:
        if t.lower().startswith(prefix):
            return t.split(":", 1)[1].strip()
    return ""


def derive_product_code(product: dict) -> str:
    """
    商品编码 = tag 'style_colour'（款号7位 + 颜色4位，如 WTRVS27ECRU）。
    少数商品没有这个 tag，则取所有 variant SKU 的公共前缀（SKU = style_colour + 尺码）。
    """
    code = tag_value(product.get("tags") or [], "style_colour")
    if code:
        return code.upper()

    skus = [v.get("sku") or "" for v in product.get("variants") or [] if v.get("sku")]
    if skus:
        m = re.match(r"^([A-Z]{5}\d{2}[A-Z0-9]{4})", skus[0].upper())
        if m:
            return m.group(1)
        if len(skus) > 1:
            prefix = skus[0]
            for s in skus[1:]:
                while not s.startswith(prefix):
                    prefix = prefix[:-1]
            if len(prefix) >= 6:
                return prefix.upper()
        return re.sub(r"(OS|ONESIZE)$", "", skus[0].upper())

    return re.sub(r"[^A-Za-z0-9]+", "_", product.get("handle") or "UNKNOWN").upper()


def video_urls(product: dict) -> List[str]:
    """
    商品视频（media_type == "video"，Shopify 自托管），每个视频取分辨率最高的 mp4。
    external_video（YouTube/Vimeo 外链）无法直接下载，忽略。
    """
    urls: List[str] = []
    for m in product.get("media") or []:
        if m.get("media_type") != "video":
            continue
        mp4s = [s for s in m.get("sources") or [] if s.get("format") == "mp4" and s.get("url")]
        if not mp4s:
            continue
        best = max(mp4s, key=lambda s: (s.get("height") or 0, s.get("width") or 0))
        url = best["url"]
        if url.startswith("//"):
            url = "https:" + url
        if url not in urls:
            urls.append(url)
    return urls


def image_urls(product: dict) -> List[str]:
    """按站点展示顺序返回原图 URL（去掉 ?v=，补 https:）"""
    urls: List[str] = []
    for src in product.get("images") or []:
        if isinstance(src, dict):
            src = src.get("src") or ""
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        src = src.split("?")[0]
        if src not in urls:
            urls.append(src)
    return urls
