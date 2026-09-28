# -*- coding: utf-8 -*-
"""
TOAST 尺码表抓取 → SIZE_CHART_DIR/{编码}_size.json + {编码}_size.html

数据来源（商品页 HTML，/products/{handle}.js 里没有）：
1) 成衣实测（individual）：<script js-product-json> 里的 individualSizeChart
       [{"Title": "Front length (CM)", "Size": "XS", "Measurement": "61"}, ...]
   只有部分商品有（多为上衣/连衣裙/外套等）。
2) 尺码对照 + 身体尺寸（group）：.size-chart__product-group-chart 里的 <table>，
   按商品 tag "size-chart: xxx" 共用（如 womens-fitted-sizes）。只保留 CM 列，去掉 INCHES 列。

两者都没有的商品（多数配件）只写 json（标记为无尺码表，便于断点续跑时跳过），不生成 html。
HTML 转图片见 brands/toast/pipeline/tool_sizechart_to_image.py。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from config import TOAST
from brands.toast.shopify_api import derive_product_code, get_html, tag_value
from brands.toast.size_chart_html import build_size_chart_html

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SIZE_DIR = Path(TOAST["SIZE_CHART_DIR"])
TXT_DIR = Path(TOAST["TXT_DIR"])


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _fmt_num(v) -> str:
    """与站点 JS 一致：parseFloat 后去掉多余的 0（61.0 → 61）"""
    try:
        f = float(str(v).strip())
        return str(int(f)) if f == int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return _clean(str(v))


# ================= 解析 =================
def parse_individual(items: Optional[list]) -> Optional[dict]:
    if not items:
        return None
    titles: List[str] = []
    sizes: List[str] = []
    grid: Dict[str, Dict[str, str]] = {}
    for it in items:
        t = _clean(it.get("Title") or "")
        s = _clean(str(it.get("Size") or ""))
        if not t or not s:
            continue
        if t not in titles:
            titles.append(t)
        if s not in sizes:
            sizes.append(s)
        grid.setdefault(s, {})[t] = _fmt_num(it.get("Measurement"))
    if not titles:
        return None
    rows = [[s] + [grid[s].get(t, "-") for t in titles] for s in sizes]
    return {"header": ["Size"] + titles, "rows": rows}


def _header_cells(tr) -> List[str]:
    header: List[str] = []
    for td in tr.find_all(["td", "th"]):
        span = int(td.get("colspan") or 1)
        title_el = td.select_one(".sizeTitle")
        if title_el and span >= 2:
            name = _clean(title_el.get_text())
            # 按 DOM 顺序展开单位子列（通常 CM 在前、INCHES 在后）
            units = []
            for div in td.find_all("div"):
                cls = " ".join(div.get("class") or [])
                if "sizeCM" in cls:
                    units.append("CM")
                elif "sizeInches" in cls:
                    units.append("IN")
            units = (units + ["?"] * span)[:span]
            header += [f"{name} ({u})" for u in units]
        else:
            text = _clean(td.get_text(" "))
            header += [text] * span
    return header


def _is_inch_col(h: str) -> bool:
    return bool(re.search(r"\((IN|INS|INCH|INCHES)\)|\binch", h, flags=re.I))


def parse_group(el) -> List[dict]:
    if el is None:
        return []
    tables: List[dict] = []
    for table in el.find_all("table"):
        trs = [tr for tr in table.find_all("tr") if tr.find(["td", "th"])]
        if len(trs) < 2:
            continue
        header = _header_cells(trs[0])
        rows = [[_clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])] for tr in trs[1:]]
        rows = [r for r in rows if any(r)]

        keep = [i for i, h in enumerate(header) if not _is_inch_col(h)]
        header = [header[i] for i in keep]
        rows = [[r[i] if i < len(r) else "" for i in keep] for r in rows]

        # 男装表把 XS/S/M 这种字母码放在 "UK" 列下，这列其实就是尺码
        if header and rows and all(re.fullmatch(r"X*[SML]|X+L|\d?XL", r[0] or "", flags=re.I) for r in rows):
            header[0] = "Size"

        title_el = table.find_previous(["p", "h4", "h5"])
        title = _clean(title_el.get_text()) if title_el and el in title_el.parents else ""
        note_el = table.find_next("p", class_="size-chart__individual-chart-subheading")
        note = _clean(note_el.get_text()) if note_el and el in note_el.parents else ""

        tables.append({"title": title, "header": header, "rows": rows, "note": note})
    return tables


def parse_size_chart_page(page_html: str, url: str) -> dict:
    soup = BeautifulSoup(page_html, "html.parser")
    pj_el = soup.select_one("[js-product-json]")
    if pj_el is None:
        raise RuntimeError("页面里没有 js-product-json（可能被 Cloudflare 拦截或页面改版）")
    product = json.loads(pj_el.string or pj_el.get_text())

    tags = product.get("tags") or []
    return {
        "code": derive_product_code(product),
        "name": _clean((product.get("title") or "").split("|")[0]),
        "gender": tag_value(tags, "gender"),
        "style_category": product.get("type") or "",
        "size_chart_tag": tag_value(tags, "size-chart"),
        "source_url": url,
        "individual": parse_individual(product.get("individualSizeChart")),
        "group": parse_group(soup.select_one(".size-chart__product-group-chart")),
    }


# ================= 写文件 =================
def write_size_chart(data: dict, out_dir: Path = SIZE_DIR) -> Optional[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    code = data["code"]
    with open(out_dir / f"{code}_size.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    page = build_size_chart_html(data)
    if not page:
        return None
    html_path = out_dir / f"{code}_size.html"
    html_path.write_text(page, encoding="utf-8")
    return html_path


def rebuild_size_chart_html(out_dir: Path = SIZE_DIR) -> int:
    """只改了页面样式/翻译时用：从已有 json 重新生成全部 html，不再请求网站"""
    n = 0
    for p in sorted(Path(out_dir).glob("*_size.json")):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        page = build_size_chart_html(data)
        if page:
            (p.parent / f"{data['code']}_size.html").write_text(page, encoding="utf-8")
            n += 1
    print(f"🔁 重新生成 {n} 个尺码表页面 → {out_dir}")
    return n


# ================= 入口 =================
def _urls_from_links(links_file: Path, only_clothing: bool) -> List[str]:
    with open(links_file, "r", encoding="utf-8") as f:
        urls = list(dict.fromkeys(u.strip() for u in f if u.strip()))
    if not only_clothing:
        return urls
    meta_path = links_file.with_name("links_meta.json")
    if not meta_path.exists():
        return urls
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return [u for u in urls if any("clothing" in c for c in (meta.get(u) or {}).get("collections", []))]


def _urls_from_codes(codes_file: Path) -> List[str]:
    urls: List[str] = []
    with open(codes_file, "r", encoding="utf-8") as f:
        codes = [re.sub(r"\s+", "", c).upper() for c in f if c.strip()]
    for code in dict.fromkeys(codes):
        txt = TXT_DIR / f"{code}.txt"
        url = None
        if txt.exists():
            for line in txt.read_text(encoding="utf-8").splitlines():
                if line.startswith("Source URL:"):
                    url = line.split(":", 1)[1].strip()
                    break
        if url:
            urls.append(url)
        else:
            print(f"⚠️ 找不到 TXT / Source URL，跳过：{code}")
    return urls


def _done_urls(out_dir: Path) -> set:
    done = set()
    for p in out_dir.glob("*_size.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                done.add(json.load(f).get("source_url"))
        except Exception:
            pass
    return done


def toast_fetch_size_charts(
    links_file: Optional[Path] = None,
    codes_file: Optional[Path] = None,
    only_clothing: bool = True,
    overwrite: bool = False,
    out_dir: Optional[Path] = None,
) -> None:
    """
    - 默认读 LINKS_FILE，只抓衣服类目（配件基本没有尺码表），only_clothing=False 则全抓
    - 传 codes_file 时只抓这些编码（编码 → TXT 里的 Source URL）
    - 已抓过的（json 已存在）默认跳过，中途被 Cloudflare 打断后直接重跑即可续上
    - 顺序请求（全局节流），不要开并发
    """
    out_dir = Path(out_dir or SIZE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if codes_file:
        urls = _urls_from_codes(Path(codes_file))
    else:
        urls = _urls_from_links(Path(links_file or TOAST["LINKS_FILE"]), only_clothing)

    if not overwrite:
        done = _done_urls(out_dir)
        skipped = sum(1 for u in urls if u in done)
        urls = [u for u in urls if u not in done]
        if skipped:
            print(f"⏭️ 已抓过 {skipped} 个，跳过")

    print(f"📦 待抓尺码表 {len(urls)} 个 → {out_dir}")
    n_html = n_empty = n_fail = 0
    for i, url in enumerate(urls, 1):
        try:
            data = parse_size_chart_page(get_html(url), url)
            html_path = write_size_chart(data, out_dir)
            if html_path:
                n_html += 1
                kinds = "+".join(k for k in ("individual", "group") if data.get(k))
                print(f"✅ {i:04d} {data['code']}: {kinds}")
            else:
                n_empty += 1
                print(f"➖ {i:04d} {data['code']}: 无尺码表")
        except Exception as e:
            n_fail += 1
            print(f"💥 {i:04d} {url}: {e}")
            if "Cloudflare" in str(e):
                print("⛔ 被 Cloudflare 持续拦截，停止本次抓取；稍后重跑会从断点继续")
                break

    print(f"🎯 完成：生成页面 {n_html}，无尺码表 {n_empty}，失败 {n_fail}，目录：{out_dir}")


if __name__ == "__main__":
    toast_fetch_size_charts()
