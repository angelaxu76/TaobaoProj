# -*- coding: utf-8 -*-
"""
每个请求都新建一个 driver 的栈类型探针：
- 复用 houseoffraser_fetch_info.get_driver / _classify_stack_by_html_head
- 访问同一 URL N 次（默认 100），间隔 2 秒
- 将每次 HTML 保存到 D:/temp/pages/{idx}_{ver}.html
"""

import sys
import time
from collections import Counter
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ★ 复用你现有脚本中的配置与判定函数
from barbour.supplier.houseoffraser_fetch_info import get_driver, _classify_stack_by_html_head  # noqa: E402

OUT_DIR = Path("D:/temp/pages")

def probe_per_request(url: str, repeat: int = 100, wait_html: int = 8, interval_sec: float = 2.0, headless: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counter = Counter()

    for i in range(1, repeat + 1):
        driver = get_driver(headless=headless)  # ★ 每次新建浏览器实例
        try:
            driver.get(url)
            WebDriverWait(driver, wait_html).until(
                EC.presence_of_element_located((By.TAG_NAME, "html"))
            )
            html = driver.page_source or ""
            ver = _classify_stack_by_html_head(html)  # 'new' / 'legacy' / 'unknown'

            # 保存页面
            out = OUT_DIR / f"{i:03d}_{ver}.html"
            out.write_text(html, encoding="utf-8", errors="ignore")

            counter[ver] += 1
            print(f"[{i}/{repeat}] {ver} -> {out}")
        except Exception as e:
            counter["error"] += 1
            print(f"[{i}/{repeat}] error: {e}")
        finally:
            # ★ 彻底关闭这个请求对应的浏览器
            try:
                driver.quit()
            except Exception:
                pass

        time.sleep(interval_sec)

    # 汇总
    print("\n=== 统计结果 ===")
    for k in ("new", "legacy", "unknown", "error"):
        if counter[k]:
            print(f"{k}: {counter[k]}")
    print(f"total: {sum(counter.values())}")

if __name__ == "__main__":
    # 可传参：python test_stack_probe.py "<URL>" [repeat]
    if len(sys.argv) >= 2:
        url = sys.argv[1]
        repeat = int(sys.argv[2]) if len(sys.argv) >= 3 else 100
        probe_per_request(url, repeat=repeat, wait_html=8, interval_sec=2.0, headless=False)
    else:
        # 不传参时用一个示例 URL，避免 SystemExit
        url = "https://www.houseoffraser.co.uk/brand/barbour-international/boys-govan-quilted-jacket-623747#colcode=62374703"
        probe_per_request(url, repeat=100, wait_html=8, interval_sec=2.0, headless=False)
