import time
from collections import Counter
from pathlib import Path

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === 复用你原来的判别逻辑 ===
def classify_stack_by_html_head(html: str) -> str:
    head = html[:8192].lower()
    if ('class="fraserspx"' in head) or ('data-recs-provider="graphql"' in head) or ('/_next/static/' in head):
        return "new"
    if ('xmlns="http://www.w3.org/1999/xhtml"' in head) or ('/wstatic/dist/' in head) or ('var datalayerdata' in head):
        return "legacy"
    return "unknown"

def get_driver(headless=True):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--start-maximized")
    return uc.Chrome(options=options)

def test_url_stack(url: str, repeat: int = 100, wait_html: int = 8):
    counter = Counter()
    driver = get_driver(headless=True)
    try:
        for i in range(repeat):
            try:
                driver.get(url)
                WebDriverWait(driver, wait_html).until(
                    EC.presence_of_element_located((By.TAG_NAME, "html"))
                )
                html = driver.page_source
                ver = classify_stack_by_html_head(html)
                counter[ver] += 1
                print(f"[{i+1}/{repeat}] {ver}")
                # 给网站一点喘息，避免风控
                time.sleep(0.5)
            except Exception as e:
                print(f"[{i+1}] error: {e}")
                counter["error"] += 1
    finally:
        driver.quit()
    return counter

if __name__ == "__main__":
    url = "https://www.houseoffraser.co.uk/brand/barbour-international/arlo-overshirt-601028#colcode=60102803"
    result = test_url_stack(url, repeat=100)
    print("\n=== 统计结果 ===")
    for k, v in result.items():
        print(f"{k}: {v}")
