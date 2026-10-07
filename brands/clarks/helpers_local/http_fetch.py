"""
Clarks 页面抓取：先用带完整浏览器请求头的 requests；被反爬拒绝（403）后，
本次运行内切换为 Selenium（真实 Chrome）抓取。
"""
import time

import requests

from common.browser.driver_auto import build_uc_driver

# 普通 Selenium / headless 会被 Cloudflare 识别，需 undetected_chromedriver + 可见窗口
SELENIUM_HEADLESS = False
SELENIUM_PAGE_WAIT = 2

# 只带 "Mozilla/5.0" 会被 Clarks 反爬识别并返回 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_session = requests.Session()
_session.headers.update(HEADERS)
_use_selenium = False


class PageNotFound(Exception):
    pass


_driver = None


def _is_blocked(driver):
    title = (driver.title or "").lower()
    return any(k in title for k in ("access denied", "forbidden", "attention required", "just a moment"))


def _get_driver():
    global _driver
    if _driver is None:
        _driver = build_uc_driver(headless=SELENIUM_HEADLESS, verbose=False)
        _driver.set_page_load_timeout(30)
    return _driver


def _fetch_selenium(url):
    driver = _get_driver()
    driver.get(url)
    time.sleep(SELENIUM_PAGE_WAIT)
    if _is_blocked(driver):
        # 浏览器也被拦：换一个新浏览器再试一次
        close()
        driver = _get_driver()
        driver.get(url)
        time.sleep(SELENIUM_PAGE_WAIT)
        if _is_blocked(driver):
            raise RuntimeError(f"Selenium 也被拦截（页面标题: {driver.title}）")
    return driver.page_source


def fetch_html(url, timeout=15):
    """返回页面 HTML；404 抛 PageNotFound，其他失败抛异常。"""
    global _use_selenium
    if not _use_selenium:
        r = _session.get(url, timeout=timeout)
        if r.status_code == 404:
            raise PageNotFound(url)
        if r.status_code != 403:
            r.raise_for_status()
            return r.text
        print("⚠️ requests 被拒（403），本次运行改用 Selenium 抓取")
        _use_selenium = True
    return _fetch_selenium(url)


def close():
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
