# -*- coding: utf-8 -*-
"""
REISS 商品链接抓取（健壮版，异常也会保存结果）
- 首页无 p；第二页起 ?p=1,2,3...
- 多类目入口；pipeline 可调用
- 每页增量写入；异常/退出时最终写入
"""

from __future__ import annotations
import time
import random
import re
from typing import Iterable, List, Set
from pathlib import Path
import os, time, datetime, errno

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager

# ==== 可从 config 读取，没配也能跑 ====
try:
    from config import REISS
    DEFAULT_OUTPUT = Path(REISS["LINKS_FILE"])
    DEFAULT_CATEGORIES = REISS.get("CATEGORY_BASE_URLS", [])
except Exception:
    DEFAULT_OUTPUT = Path(r"D:/TB/Products/REISS/publication/product_links.txt")
    DEFAULT_CATEGORIES = []

# ==== 参数 ====
WAIT_FIRST = 12       # 首页等待
WAIT_EACH = 6         # 翻页等待
MAX_EMPTY_PAGES = 2   # 连续空页阈值（或无新增）
HEADLESS_DEFAULT = True

def _new_driver(headless: bool = HEADLESS_DEFAULT) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # 如果你想彻底消除 WebGL/ANGLE 的报错，可按需打开下面两行（牺牲部分安全/渲染能力）
    # options.add_argument("--enable-unsafe-swiftshader")
    # options.add_argument("--use-angle=swiftshader")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    })
    return driver

def _build_page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    sep = '&' if '?' in base_url else '?'
    return f"{base_url}{sep}p={page-1}"

def _wait_list_loaded(driver: webdriver.Chrome, first: bool = False) -> None:
    timeout = WAIT_FIRST if first else WAIT_EACH
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.MuiCardMedia-root")))
    except Exception:
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'a[href^="/style/"], a[href^="https://www.reiss.com/style/"]')
        ))

def _extract_links(driver: webdriver.Chrome) -> Set[str]:
    links: Set[str] = set()
    for a in driver.find_elements(By.CSS_SELECTOR, "a.MuiCardMedia-root"):
        href = (a.get_attribute("href") or "").strip()
        if href.startswith("https://www.reiss.com/style/"):
            links.add(href.split("#")[0].rstrip("/"))
    for a in driver.find_elements(By.CSS_SELECTOR, 'a[href^="/style/"], a[href^="https://www.reiss.com/style/"]'):
        href = (a.get_attribute("href") or "").strip()
        if "/style/" in href:
            if href.startswith("/"):
                href = "https://www.reiss.com" + href
            links.add(href.split("#")[0].rstrip("/"))
    return links


# 替换原来的 _atomic_write 为这个“Windows 安全”的版本


def _safe_write(out_path: Path, lines: List[str], max_retries: int = 6, backoff: float = 0.4) -> None:
    """
    Windows 友好的安全写入：
    1) 写到唯一临时文件
    2) 多次重试 os.replace() 覆盖目标
    3) 若仍然 PermissionError(WinError 5)，写到 fallback 文件，保证这次抓到的数据可用
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) 写唯一临时文件
    tmp = out_path.with_suffix(out_path.suffix + f".tmp.{os.getpid()}.{int(time.time()*1000)}")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")

    # 2) 多次重试 replace
    for attempt in range(1, max_retries + 1):
        try:
            os.replace(tmp, out_path)  # 原子替换
            return
        except PermissionError as e:
            # 常见：目标文件被编辑器/杀毒占用；稍等重试
            if attempt == max_retries:
                break
            time.sleep(backoff * attempt)
        except OSError as e:
            # 其它偶发错误也重试几次
            if attempt == max_retries:
                break
            time.sleep(backoff * attempt)

    # 3) 仍失败：落盘到 fallback，确保有结果
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fb = out_path.with_name(f"{out_path.stem}.fallback-{ts}.txt")
    try:
        with fb.open("w", encoding="utf-8", newline="\n") as f:
            for line in lines:
                f.write(line + "\n")
        print(f"⚠️ 无法覆盖 {out_path.name}（可能被占用），已写入备份文件：{fb}")
    finally:
        # 清理临时文件
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _slug(url: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', url.lower()).strip('-')[:80]

def _maybe_restart_and_retry(driver, headless, page_url, first_wait) -> tuple[webdriver.Chrome, set]:
    """重启浏览器并重试当前页一次；返回(新driver, links)。失败则抛异常"""
    try:
        driver.quit()
    except Exception:
        pass
    driver = _new_driver(headless=headless)
    driver.get(page_url)
    _wait_list_loaded(driver, first=first_wait)
    links = _extract_links(driver)
    return driver, links

def reiss_get_links(
    category_base_urls: Iterable[str] | None = None,
    output_file: str | Path | None = None,
    headless: bool = HEADLESS_DEFAULT,
    max_pages_per_cat: int = 500,
    use_swiftshader: bool = False,   # ✅ 可选：压制 GPU 报错
) -> Path:
    cats: List[str] = [u.strip() for u in (category_base_urls or DEFAULT_CATEGORIES) if u and u.strip()]
    if not cats:
        raise ValueError("请传入 category_base_urls，或在 REISS['CATEGORY_BASE_URLS'] 配置类目首页 URL（无 p）。")

    out_path = Path(output_file) if output_file else DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 可选开启 SwiftShader
    if use_swiftshader:
        orig_new = _new_driver
        def _new_driver_swiftshader(headless: bool = HEADLESS_DEFAULT):
            options = webdriver.ChromeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("--enable-unsafe-swiftshader")
            options.add_argument("--use-angle=swiftshader")
            drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            })
            return drv
        globals()["_new_driver"] = _new_driver_swiftshader  # 动态替换

    all_links: Set[str] = set()
    driver: webdriver.Chrome | None = None

    try:
        driver = _new_driver(headless=headless)

        for idx, base in enumerate(cats, 1):
            print(f"\n▶ 类目 [{idx}/{len(cats)}]: {base}")
            cat_links: Set[str] = set()
            cat_file = out_path.with_name(f"links_{_slug(base)}.txt")
            empty_streak = 0

            try:
                for page in range(1, max_pages_per_cat + 1):
                    page_url = _build_page_url(base, page)
                    print(f"🌐 第 {page} 页：{page_url}")

                    try:
                        driver.get(page_url)
                        _wait_list_loaded(driver, first=(page == 1))
                        links = _extract_links(driver)
                    except Exception as e:
                        print(f"💥 本页异常：{e} → 尝试重启浏览器并重试一次…")
                        try:
                            driver, links = _maybe_restart_and_retry(driver, headless, page_url, first_wait=(page == 1))
                            print("   🔁 重试成功。")
                        except Exception as e2:
                            print(f"   💣 重试仍失败：{e2} → 结束本类目，继续下一个。")
                            # 写入类目级与总级文件的当前累计
                            _safe_write(cat_file, sorted(cat_links))
                            _safe_write(out_path, sorted(all_links))
                            break  # 结束本类目

                    before_all = len(all_links)
                    before_cat = len(cat_links)
                    all_links.update(links)
                    cat_links.update(links)
                    added_all = len(all_links) - before_all
                    added_cat = len(cat_links) - before_cat

                    print(f"   ✅ 抓到 {len(links)} 条，本页新增(类目) {added_cat} 条，累计(总) {len(all_links)}")

                    # 每页增量写盘：类目级 + 总汇总
                    _safe_write(cat_file, sorted(cat_links))
                    _safe_write(out_path, sorted(all_links))

                    # 连续两页无新增，结束本类目
                    if added_cat == 0:
                        empty_streak += 1
                    else:
                        empty_streak = 0
                    if empty_streak >= MAX_EMPTY_PAGES:
                        print(f"   ⏹️ 连续 {MAX_EMPTY_PAGES} 页无新增，结束本类目")
                        break

                    time.sleep(random.uniform(0.6, 1.2))

            except Exception as e_cat:
                # 类目级兜底：无论发生什么，继续下一个类目
                print(f"🚧 类目级异常：{e_cat} → 跳过该类目余下页面。")
                _safe_write(cat_file, sorted(cat_links))
                _safe_write(out_path, sorted(all_links))
                continue

    except Exception as e:
        print(f"💣 全局异常：{e}")
    finally:
        try:
            _safe_write(out_path, sorted(all_links))
            print(f"📝 已最终保存 {len(all_links)} 条 → {out_path}")
        except Exception as _e:
            print(f"⚠️ 写文件失败：{_e}")
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

    return out_path

# 直接运行示例
if __name__ == "__main__":
    cats = DEFAULT_CATEGORIES or [
        "https://www.reiss.com/shop/feat-sale-gender-women-0",
        "https://www.reiss.com/shop/feat-sale-gender-men-0",
    ]
    reiss_get_links(cats, headless=True)
