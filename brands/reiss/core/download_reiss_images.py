# -*- coding: utf-8 -*-
"""
REISS 图片下载脚本（Selenium 版本，兼容 REISS 命名：去横线、抓 preload）

- 从 codes_file 读取商品编码
- 在 TXT_DIR 找到对应 TXT，解析 URL
- 用 Selenium 打开商品页，拿到 HTML
- BeautifulSoup 汇总 <img src> / data-* / srcset / <link rel=preload imagesrcset>
- 过滤：文件名需包含字母 "s" 且包含「归一化后的编码」（去掉非字母数字）
- requests 下载到 IMAGE_DOWNLOAD
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, List, Tuple, Set

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from config import BRAND_CONFIG, GLOBAL_CHROMEDRIVER_PATH

# ===== 配置 =====
REISS_CFG = BRAND_CONFIG["reiss"]  # 专用
HEADLESS = True  # 是否无头运行

# ===== 启动 Selenium 浏览器 =====
def make_driver(headless: bool = HEADLESS):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(service=Service(GLOBAL_CHROMEDRIVER_PATH), options=options)
    return driver

# ===== 工具函数 =====


def format_reiss_code(code: str) -> str:
    """
    把编码规范化为 REISS 展示样式：
    e.g. 'W22548' / 'W22-548' -> 'W22-548'
    """
    z = re.sub(r'[^A-Za-z0-9]+', '', (code or ''))
    m = re.match(r'^([A-Za-z]+)(\d{2})(\d{3})$', z, flags=re.I)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}-{m.group(3)}"
    return code

def derive_suffix_from_fname(fname: str) -> str:
    """
    从原始文件名里提取 s 后缀：
    - 'W22548s.jpg'   -> 's'
    - 'W22548s6.jpg'  -> 's6'
    - 兜底：若仅有 _数字 / -数字 结尾，则转成 s数字；再兜底为 's'
    """
    stem = Path(fname).stem
    m = re.search(r'([sS]\d*)$', stem)
    if m:
        return m.group(1).lower()
    m = re.search(r'[_-](\d+)$', stem)
    if m:
        return f"s{m.group(1)}"
    return "s"


def read_codes(codes_file: Path) -> List[str]:
    with open(codes_file, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def find_txt_for_code(txt_dir: Path, code: str) -> Optional[Path]:
    exact = txt_dir / f"{code}.txt"
    if exact.exists():
        return exact
    candidates = list(txt_dir.glob(f"*{code}*.txt"))
    if candidates:
        candidates.sort(key=lambda p: len(p.name))
        return candidates[0]
    return None

def parse_url_from_txt(txt_path: Path) -> Optional[str]:
    url_pat = re.compile(r"(https?://\S+)")
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            m = url_pat.search(line)
            if m:
                return m.group(1)
    return None

def _norm(s: str) -> str:
    """归一化比较用：全小写 + 去掉非字母数字"""
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def extract_codes_from_url(url: str) -> List[str]:
    """把 URL 各段作为候选编码（尤其是最后一段）"""
    try:
        path = url.split("://", 1)[-1].split("/", 1)[-1]  # 去域名
    except Exception:
        return []
    parts = [p for p in path.split("/") if p]
    cands = []
    for p in parts:
        if re.match(r"^[A-Za-z0-9_-]+$", p):
            cands.append(p.lower())
    # 去重保持顺序
    seen = set(); uniq = []
    for c in cands:
        if c not in seen:
            uniq.append(c); seen.add(c)
    return uniq

def download_image(img_url: str, out_dir: Path, out_name: str | None = None):
    try:
        resp = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=15)
        resp.raise_for_status()

        # 原始扩展名
        src_name = os.path.basename(img_url.split("?")[0])
        src_ext = os.path.splitext(src_name)[1].lower() or ".jpg"

        # 目标文件名
        filename = (out_name if out_name else src_name)
        if os.path.splitext(filename)[1] == "":
            filename += src_ext  # 保证有扩展名

        out_path = out_dir / filename
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(1024 * 16):
                if chunk:
                    f.write(chunk)
        print(f"✅ 图片已保存: {out_path}")
    except Exception as e:
        print(f"❌ 图片下载失败 [{img_url}]: {e}")


def parse_candidate_image_urls(soup: BeautifulSoup) -> List[str]:
    """从页面尽可能多地收集图片 URL（img/src, data-*, srcset, preload/imagesrcset）"""
    candidates: Set[str] = set()

    # <img src> + 常见懒加载属性
    for img in soup.find_all("img"):
        src = img.get("src")
        if src: candidates.add(src)
        for k in ("data-src", "data-original", "data-lazy", "data-zoom-image"):
            v = img.get(k)
            if v: candidates.add(v)

    # srcset
    for tag in soup.find_all(["img", "source"]):
        srcset = tag.get("srcset")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            candidates.update(parts)

    # <link rel="preload" as="image" imagesrcset="...">
    for link in soup.find_all("link", rel=lambda v: v and "preload" in v, attrs={"as": "image"}):
        srcset = link.get("imagesrcset")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            candidates.update(parts)

    # 清洗：补协议、去 query、忽略相对链接
    cleaned: List[str] = []
    for u in candidates:
        if not u: continue
        if u.startswith("//"): u = "https:" + u
        if u.startswith("/"):  # 相对路径这里先忽略
            continue
        cleaned.append(u.split("?")[0])

    # 去重保持顺序
    seen = set(); uniq = []
    for u in cleaned:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

def extract_and_download_images(html: str, url: str, code: str, image_dir: Path, debug_dir: Path):
    soup = BeautifulSoup(html, "html.parser")

    # 候选编码集合：文件里的 code + URL 段落（如 an6312）
    candidates = {code.lower()}
    for c in extract_codes_from_url(url):
        candidates.add(c)
    cand_norm = {_norm(c) for c in candidates if c}  # 归一化

    urls = parse_candidate_image_urls(soup)

    matched: List[str] = []
    for u in urls:
        fname = os.path.basename(u)
        if "s" not in fname.lower():  # 保持你的旧规则：文件名里要有字母 s
            continue
        f_norm = _norm(fname)
        if any(cn and cn in f_norm for cn in cand_norm):
            matched.append(u)

    if matched:
        display_code = format_reiss_code(code)  # 例如 'W22-548'
        seen = set()
        for idx, img_url in enumerate(matched, 1):
            fname = os.path.basename(img_url.split("?")[0])
            suffix = derive_suffix_from_fname(fname)  # e.g. 's' / 's6'
            ext = os.path.splitext(fname)[1].lower() or ".jpg"

            # 目标名：W22-548_s6.jpg
            out_name = f"{display_code}_{suffix}{ext}"

            # 避免重复命名（极端情况下同后缀重复）
            if out_name.lower() in seen:
                out_name = f"{display_code}_{suffix}_{idx}{ext}"
            seen.add(out_name.lower())

            download_image(img_url, image_dir, out_name=out_name)
    else:
        print(f"⚠ 未找到任何图片 [{code}]，保存 HTML 以便排查")
        debug_file = debug_dir / f"{_norm(code) or code}.html"
        debug_file.write_text(html, encoding="utf-8", errors="ignore")


# ===== 主流程 =====
def download_reiss_images_from_codes(codes_file: Path):
    txt_dir = Path(REISS_CFG["TXT_DIR"])
    image_dir = Path(REISS_CFG["IMAGE_DOWNLOAD"])
    debug_dir = codes_file.parent / "DEBUG"

    image_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    codes = read_codes(codes_file)
    print(f"🚀 REISS 图片下载（Selenium） | 共 {len(codes)} 个编码")

    driver = make_driver()
    for idx, code in enumerate(codes, 1):
        print(f"\n[{idx}/{len(codes)}] ===== {code} =====")
        txt_path = find_txt_for_code(txt_dir, code)
        if not txt_path:
            print(f"⚠ 未找到 TXT：{code}")
            continue
        url = parse_url_from_txt(txt_path)
        if not url:
            print(f"⚠ TXT 未解析到 URL：{code}")
            continue

        try:
            driver.get(url)
            time.sleep(3)  # 让首屏/预加载完成
            html = driver.page_source
            extract_and_download_images(html, url, code, image_dir, debug_dir)
        except Exception as e:
            print(f"❌ 页面加载失败：{url} | {e}")

    driver.quit()
    print(f"\n✅ 完成：图片保存在 {image_dir}")

# ===== 直接运行 =====
if __name__ == "__main__":
    sample_codes_file = Path(r"D:\TB\Products\reiss\repulibcation\publication_codes_outerwear.txt")
    download_reiss_images_from_codes(sample_codes_file)
