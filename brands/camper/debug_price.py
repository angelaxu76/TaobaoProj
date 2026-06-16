# -*- coding: utf-8 -*-
"""
camper 价格调试脚本：打印页面上所有价格相关数据，帮助定位折扣价在哪里。
直接运行即可，不依赖多线程。
"""
import sys, json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root

from common.browser.driver_auto import build_uc_driver

URL = "https://www.camper.com/en_GB/women/shoes/tas/camper-tasha-K201659-012"

driver = build_uc_driver(headless=False)   # 有头，方便观察
try:
    driver.get(URL)
    time.sleep(5)   # 等页面 JS 水化完成

    # ── 1. SSR __NEXT_DATA__ (HTML 里的原始 JSON) ──────────────────────────
    ssr_raw = driver.execute_script(
        "var el=document.querySelector('script#__NEXT_DATA__');"
        "return el ? el.textContent : null;"
    )
    ssr = json.loads(ssr_raw) if ssr_raw else {}
    ps_ssr = ssr.get("props", {}).get("pageProps", {}).get("productSheet") or {}
    print("=== SSR productSheet.prices ===")
    print(json.dumps(ps_ssr.get("prices", {}), indent=2))

    # 扫描 productSheet 中所有含数字的 key，防止折扣藏在别处
    print("\n=== SSR productSheet 全部字段(只显示含数字的) ===")
    def _scan(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _scan(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan(v, f"{path}[{i}]")
        else:
            s = str(obj)
            if re.search(r"\b(96|120)\b", s):
                print(f"  {path} = {s!r}")
    _scan(ps_ssr)

    # ── 2. window.__NEXT_DATA__ (JS 水化后) ───────────────────────────────
    rt = driver.execute_script("return window.__NEXT_DATA__")
    ps_rt = (rt or {}).get("props", {}).get("pageProps", {}).get("productSheet") or {}
    print("\n=== Runtime productSheet.prices ===")
    print(json.dumps(ps_rt.get("prices", {}), indent=2))
    print("\n=== Runtime productSheet 全部字段(只显示含96或120的) ===")
    _scan(ps_rt)

    # ── 3. JSON-LD ─────────────────────────────────────────────────────────
    ld_scripts = driver.execute_script("""
        var out = [];
        document.querySelectorAll('script[type="application/ld+json"]').forEach(function(s){
            try { out.push(JSON.parse(s.textContent)); } catch(e) {}
        });
        return out;
    """)
    print("\n=== JSON-LD blocks ===")
    for block in (ld_scripts or []):
        print(json.dumps(block, indent=2, ensure_ascii=False)[:800])

    # ── 4. DOM 价格元素 ────────────────────────────────────────────────────
    price_els = driver.execute_script("""
        var hits = [];
        document.querySelectorAll('[class*="price"],[class*="Price"],[data-testid*="price"]').forEach(function(el){
            var t = el.innerText.trim();
            if (t) hits.push({tag: el.tagName, cls: el.className, text: t});
        });
        return hits;
    """)
    print("\n=== DOM price elements ===")
    for el in (price_els or []):
        print(el)

    # ── 5. 搜索所有含 96 的文本节点 ──────────────────────────────────────
    nodes_96 = driver.execute_script("""
        var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        var hits = [];
        while(walker.nextNode()){
            var t = walker.currentNode.textContent.trim();
            if (/\b96\b/.test(t) && t.length < 100) hits.push(t);
        }
        return hits;
    """)
    print("\n=== Text nodes containing 96 ===")
    for t in (nodes_96 or []):
        print(repr(t))

finally:
    input("\n按 Enter 关闭浏览器...")
    driver.quit()
