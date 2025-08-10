# -*- coding: utf-8 -*-
import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, parse_qs
from config import BARBOUR

# ========== 可调参数 ==========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
}
TIMEOUT = 20
RETRY = 3

# 你给的 Salsify 模板（把 picture_name 放进去）
SALSIFY_TMPL = (
    "https://images.salsify.com/image/upload/"
    "s--i74AAA0n--/c_fill,w_1000,h_1334,f_auto/{name}.jpg"
)

# ========== 工具函数 ==========
def extract_code_and_name(url: str):
    """
    输入: https://www.barbour.com/gb/zola-quilted-jacket-LQU1822CR11.html
    输出: ("LQU1822CR11", "zola-quilted-jacket")
    """
    filename = os.path.basename(urlparse(url).path)  # zola-quilted-jacket-LQU1822CR11.html
    if filename.endswith(".html"):
        filename = filename[:-5]
    parts = filename.split("-")
    code = parts[-1]
    name = "-".join(parts[:-1])
    return code, name

def _expand_srcset(srcset: str):
    """解析 srcset -> [(url, width_int)]，按宽度降序"""
    items = []
    for part in srcset.split(","):
        cand = part.strip()
        if not cand:
            continue
        pieces = cand.split()
        url = pieces[0]
        width = 0
        if len(pieces) > 1 and pieces[1].endswith("w"):
            try:
                width = int(pieces[1][:-1])
            except Exception:
                width = 0
        items.append((url, width))
    items.sort(key=lambda x: x[1], reverse=True)
    return items

def _basename_no_ext(path: str) -> str:
    """
    取不带扩展名的basename，并去掉 _001/_002 之类尾缀。
    e.g. e6760d..._003.webp -> e6760d...
    """
    base = os.path.basename(urlparse(path).path)
    if "." in base:
        base = base[:base.rfind(".")]
    base = re.sub(r"_(\d{3})$", "", base)
    return base

def _is_hash_like(name: str) -> bool:
    """是否像加密名（较长的字母数字/下划线/短横线串）"""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{20,}", name))

def _uniq_keep_order(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

# ========== 提取图片链接 ==========
def extract_image_urls_ldjson(page_content: str):
    """保持原逻辑：只从 JSON-LD 的 image 数组取图"""
    soup = BeautifulSoup(page_content, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")
    if not script_tag or not script_tag.string:
        return []
    try:
        data = json.loads(script_tag.string.strip())
        images = data.get("image", [])
        if isinstance(images, list):
            return images
        elif isinstance(images, str):
            return [images]
    except Exception as e:
        print(f"[解析失败] JSON-LD 错误: {e}")
    return []

def extract_picture_hash_urls(page_content: str):
    """
    新增逻辑：从 <picture>/<img>/<source> 抓到 webp 的“哈希名”，
    拼成 Salsify URL: SALSIFY_TMPL.format(name=<hash>)
    """
    soup = BeautifulSoup(page_content, "html.parser")
    urls = []

    # 主图区域
    pictures = soup.select(".picture__wrapper picture")
    if not pictures:
        pictures = soup.find_all("picture")  # 兜底

    for pic in pictures:
        # 优先 <img src>
        img = pic.find("img")
        if img:
            for attr in ("src", "data-src"):
                val = img.get(attr)
                if val:
                    name = _basename_no_ext(val)
                    if _is_hash_like(name):
                        urls.append(SALSIFY_TMPL.format(name=name))
                    break

        # 再看 <source srcset> 最大图
        for source in pic.find_all("source"):
            srcset = source.get("srcset") or source.get("data-srcset") or ""
            if srcset:
                items = _expand_srcset(srcset)
                if items:
                    first_url = items[0][0]
                    name = _basename_no_ext(first_url)
                    if _is_hash_like(name):
                        urls.append(SALSIFY_TMPL.format(name=name))

    # 可选：散落 img 兜底
    if not urls:
        for img in soup.find_all("img"):
            for attr in ("srcset", "data-srcset"):
                if img.get(attr):
                    items = _expand_srcset(img.get(attr))
                    if items:
                        name = _basename_no_ext(items[0][0])
                        if _is_hash_like(name):
                            urls.append(SALSIFY_TMPL.format(name=name))
                            break
            for attr in ("src", "data-src"):
                if img.get(attr):
                    name = _basename_no_ext(img.get(attr))
                    if _is_hash_like(name):
                        urls.append(SALSIFY_TMPL.format(name=name))
                        break

    return _uniq_keep_order(urls)

# ========== “图片唯一标识” 生成规则 ==========
def image_identity(url: str) -> str:
    """
    用于去重的“唯一标识”：
    1) Salsify：最后一段 basename（不带扩展名），去掉 _001 等后缀
    2) media.barbour.com/i/barbour/<id>：用 <id>（去掉参数、扩展名、_001）
    3) 其它：如果 basename 像哈希则用哈希；否则回退到完整 URL（避免误合并）
    """
    parsed = urlparse(url)
    path = parsed.path
    host = (parsed.netloc or "").lower()

    base_no_ext = _basename_no_ext(path)

    # Salsify：/image/upload/.../<hash>.jpg
    if "images.salsify.com" in host:
        return base_no_ext

    # Barbour Scene7：/i/barbour/<id>...
    if "media.barbour.com" in host and path.startswith("/i/"):
        # 取 /i/barbour/<id> 的 <id> 部分
        segs = path.split("/")
        # 安全判断
        if len(segs) >= 4 and segs[2] == "barbour":
            return _basename_no_ext(segs[3])

    # 其它：如果像哈希，就用哈希；否则用完整 URL
    if _is_hash_like(base_no_ext):
        return base_no_ext

    return url  # 保守：以完整 URL 为标识，避免误合并

# ========== 下载部分 ==========
def _get_with_retry(session: requests.Session, url: str):
    last_err = None
    for _ in range(RETRY):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            time.sleep(0.8)
    raise last_err

def collect_all_image_urls(html: str):
    """
    汇总：JSON-LD + <picture>，返回按出现顺序的列表（不去重）
    """
    urls = []
    urls += extract_image_urls_ldjson(html)     # 先 JSON-LD（你的原逻辑）
    urls += extract_picture_hash_urls(html)     # 再补 <picture>
    return [u for u in urls if u]

def dedupe_by_identity(urls):
    """
    按“图片唯一标识”去重，保持首次出现顺序。
    返回：[(identity, url)] 只保留每个 identity 的第一条 URL
    """
    first_index = {}
    first_url = {}
    for idx, u in enumerate(urls):
        ident = image_identity(u)
        if ident not in first_index:
            first_index[ident] = idx
            first_url[ident] = u
    # 按首次出现顺序排序
    ordered_ids = sorted(first_index.items(), key=lambda x: x[1])
    return [(ident, first_url[ident]) for ident, _ in ordered_ids]

def download_images_for_page(session: requests.Session, page_url: str, out_dir: str, code: str, name: str):
    """
    1) 收集全部候选链接到变量
    2) 基于“加密名/唯一标识”去重
    3) 按顺序下载并按 {code}-{name}_{i}.jpg 命名
    """
    html_resp = _get_with_retry(session, page_url)
    html = html_resp.text

    # 1) 收集（你想看也可以 print 出来）
    candidates = collect_all_image_urls(html)

    # 2) 去重（基于 identity）
    unique_list = dedupe_by_identity(candidates)

    if not unique_list:
        print(f"⚠️ 未发现图片: {page_url}")
        return 0

    # 3) 下载
    count = 0
    for i, (ident, img_url) in enumerate(unique_list, 1):
        filename = f"{code}-{name}_{i}.jpg"
        save_path = os.path.join(out_dir, filename)
        try:
            img_resp = _get_with_retry(session, img_url)
            with open(save_path, "wb") as f:
                f.write(img_resp.content)
            count += 1
            print(f"✅ 已保存: {filename}  <- {ident}")
        except Exception as e:
            print(f"❌ 下载失败: {img_url} -> {filename}，错误: {e}")
    return count

# ========== 主流程 ==========
def download_barbour_images():
    links_file = BARBOUR["LINKS_FILE"]
    image_folder = BARBOUR["IMAGE_DOWNLOAD"]
    os.makedirs(image_folder, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"📦 共 {len(urls)} 个商品链接，开始依次下载...")

    with requests.Session() as session:
        for idx, url in enumerate(urls, 1):
            try:
                code, name = extract_code_and_name(url)
                saved = download_images_for_page(session, url, image_folder, code, name)
                print(f"👉 [{idx}/{len(urls)}] {url} 下载张数: {saved}")
            except Exception as e:
                print(f"❌ [{idx}/{len(urls)}] 失败: {url}，错误: {e}")

    print("🎯 所有图片处理完毕。")

if __name__ == "__main__":
    download_barbour_images()
