"""
Clarks 页面抓取：先用带完整浏览器请求头的 requests；被反爬拒绝（403）后，
本次运行内切换为 Selenium（真实 Chrome）抓取。
"""
import time

import requests

from common.browser.selenium_utils import get_driver, quit_driver

SELENIUM_HEADLESS = True  # 若 headless 仍被拦，改为 False
DRIVER_NAME = "clarks_fetch"
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


def _fetch_selenium(url):
    driver = get_driver(DRIVER_NAME, headless=SELENIUM_HEADLESS)
    driver.get(url)
    time.sleep(SELENIUM_PAGE_WAIT)
    title = (driver.title or "").lower()
    if "access denied" in title or "forbidden" in title:
        # 浏览器也被拦：换一个新浏览器再试一次
        quit_driver(DRIVER_NAME)
        driver = get_driver(DRIVER_NAME, headless=SELENIUM_HEADLESS)
        driver.get(url)
        time.sleep(SELENIUM_PAGE_WAIT)
        title = (driver.title or "").lower()
        if "access denied" in title or "forbidden" in title:
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
    quit_driver(DRIVER_NAME)
