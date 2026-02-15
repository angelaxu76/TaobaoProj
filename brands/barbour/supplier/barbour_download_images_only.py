# -*- coding: utf-8 -*-
import os
import re
import json
import time
import logging
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import BARBOUR
from PIL import Image

# ========== logging ==========
logger = logging.getLogger(__name__)
# 确保被 import 调用时也有输出（不依赖调用方配置 logging）
if not logger.handlers and not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

# ========== 可调参数 ==========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
}
TIMEOUT = 20
RETRY = 3

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
    filename = os.path.basename(urlparse(url).path)
    if filename.endswith(".html"):
        filename = filename[:-5]
    parts = filename.split("-")
    code = parts[-1]
    name = "-".join(parts[:-1])
    logger.debug("extract_code_and_name: url=%s -> code=%s, name=%s", url, code, name)
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


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def _is_salsify(url: str) -> bool:
    return "images.salsify.com" in url.lower()


# ========== 提取图片链接 ==========
def extract_image_urls_ldjson(page_content: str):
    """从 JSON-LD 的 image 数组取图"""
    soup = BeautifulSoup(page_content, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")
    if not script_tag or not script_tag.string:
        logger.debug("JSON-LD: 未找到 script[type=application/ld+json]")
        return []
    try:
        data = json.loads(script_tag.string.strip())
        images = data.get("image", [])
        if isinstance(images, str):
            images = [images]
        if isinstance(images, list):
            logger.debug("JSON-LD: 找到 %d 张图", len(images))
            return images
    except Exception as e:
        logger.warning("JSON-LD 解析失败: %s", e)
    return []


def extract_picture_hash_urls(page_content: str):
    """
    从 <picture>/<img>/<source> 抓到 webp 的"哈希名"，
    拼成 Salsify URL
    """
    soup = BeautifulSoup(page_content, "html.parser")
    urls = []

    pictures = soup.select(".picture__wrapper picture")
    if not pictures:
        pictures = soup.find_all("picture")
    logger.debug("picture_hash: 找到 %d 个 <picture> 标签", len(pictures))

    for pic in pictures:
        img = pic.find("img")
        if img:
            for attr in ("src", "data-src"):
                val = img.get(attr)
                if val:
                    name = _basename_no_ext(val)
                    if _is_hash_like(name):
                        urls.append(SALSIFY_TMPL.format(name=name))
                    break

        for source in pic.find_all("source"):
            srcset = source.get("srcset") or source.get("data-srcset") or ""
            if srcset:
                items = _expand_srcset(srcset)
                if items:
                    first_url = items[0][0]
                    name = _basename_no_ext(first_url)
                    if _is_hash_like(name):
                        urls.append(SALSIFY_TMPL.format(name=name))

    # 兜底：散落 img
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

    result = _uniq_keep_order(urls)
    logger.debug("picture_hash: 提取到 %d 个 Salsify URL", len(result))
    return result


def extract_picture_urls_by_code(page_content: str, product_code: str):
    """
    从 <picture> 内收集所有 img/source 的 src/srcset，
    仅保留包含商品编码的链接，按出现顺序去重返回。
    """
    soup = BeautifulSoup(page_content, "html.parser")
    urls, seen = [], set()

    def add(u: str):
        if not u:
            return
        base = u.split("?")[0].split("#")[0]
        if product_code in base and base not in seen:
            seen.add(base)
            urls.append(base)

    for pic in soup.find_all("picture"):
        for tag in pic.find_all(["img", "source"]):
            for attr in ("src", "data-src"):
                add(tag.get(attr))
            for attr in ("srcset", "data-srcset"):
                srcset = tag.get(attr)
                if srcset:
                    for part in srcset.split(","):
                        add(part.strip().split(" ")[0])

    logger.debug("picture_by_code(%s): 找到 %d 个含编码的链接", product_code, len(urls))
    return urls


# ========== "图片唯一标识" 生成规则 ==========
def image_identity(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    host = (parsed.netloc or "").lower()
    base_no_ext = _basename_no_ext(path)

    if "images.salsify.com" in host:
        return base_no_ext

    if "media.barbour.com" in host and path.startswith("/i/"):
        segs = path.split("/")
        if len(segs) >= 4 and segs[2] == "barbour":
            return _basename_no_ext(segs[3])

    if _is_hash_like(base_no_ext):
        return base_no_ext

    return url


# ========== 收集 & 去重 ==========
def collect_all_image_urls(html: str, product_code: str | None = None):
    """汇总：JSON-LD + <picture>(哈希名) + <picture>(含商品编码)"""
    urls = []
    urls += extract_image_urls_ldjson(html)
    urls += extract_picture_hash_urls(html)
    if product_code:
        urls += extract_picture_urls_by_code(html, product_code)
    result = [u for u in urls if u]
    logger.debug("collect_all: 共收集到 %d 个候选 URL", len(result))
    return result


def dedupe_by_identity(urls):
    """按"图片唯一标识"去重，保持首次出现顺序。"""
    first_index = {}
    first_url = {}
    for idx, u in enumerate(urls):
        ident = image_identity(u)
        if ident not in first_index:
            first_index[ident] = idx
            first_url[ident] = u
    ordered_ids = sorted(first_index.items(), key=lambda x: x[1])
    result = [(ident, first_url[ident]) for ident, _ in ordered_ids]
    logger.debug("dedupe: %d -> %d 张（去重后）", len(urls), len(result))
    return result


def filter_candidates(candidates, code):
    """只保留含商品编码的静态图 + Salsify 哈希图"""
    filtered = []
    for u in candidates:
        u0 = _strip_query(u)
        if _is_salsify(u0):
            filtered.append(u0)
        elif code.upper() in u0.upper():
            filtered.append(u0)

    if filtered:
        logger.debug("filter: %d -> %d 张（过滤后）", len(candidates), len(filtered))
        return filtered

    logger.debug("filter: 过滤后为空，回退到全部 %d 张", len(candidates))
    return candidates


# ========== 下载部分 ==========
def _get_with_retry(session: requests.Session, url: str):
    last_err = None
    for attempt in range(1, RETRY + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            logger.debug("请求失败 (第%d次): %s -> %s", attempt, url[:80], e)
            time.sleep(0.8)
    raise last_err


def download_images_for_page(session: requests.Session, page_url: str, out_dir: str, code: str, name: str):
    """收集 -> 过滤 -> 去重 -> 下载"""
    logger.info("正在处理: %s (code=%s)", page_url, code)

    html_resp = _get_with_retry(session, page_url)
    logger.debug("页面获取成功, HTTP %d, 长度 %d", html_resp.status_code, len(html_resp.text))
    html = html_resp.text

    candidates = collect_all_image_urls(html, code)
    candidates = filter_candidates(candidates, code)
    unique_list = dedupe_by_identity(candidates)

    if not unique_list:
        logger.warning("未发现图片: %s", page_url)
        return 0

    count = 0
    for i, (ident, img_url) in enumerate(unique_list, 1):
        filename = f"{code}-{name}_{i}.jpg"
        save_path = os.path.join(out_dir, filename)
        try:
            img_resp = _get_with_retry(session, img_url)
            with open(save_path, "wb") as f:
                f.write(img_resp.content)
            make_square_image(save_path, save_path)
            count += 1
            logger.info("已保存: %s <- %s", filename, ident[:60])
        except Exception as e:
            logger.error("下载失败: %s -> %s, 错误: %s", img_url[:80], filename, e)
    return count


def make_square_image(img_path: str, out_path: str, fill_color=(255, 255, 255)):
    """将图片扩展为正方形，保持原图居中，空白部分用白色填充。"""
    try:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w == h:
                img.save(out_path, quality=90)
                return
            size = max(w, h)
            canvas = Image.new("RGB", (size, size), fill_color)
            paste_x = (size - w) // 2
            paste_y = (size - h) // 2
            canvas.paste(img, (paste_x, paste_y))
            canvas.save(out_path, quality=90)
    except Exception as e:
        logger.error("方形化失败: %s, 错误: %s", img_path, e)


# ========== 多线程入口 ==========
def worker(url, image_folder):
    """每个线程独立运行，不共享 session。"""
    try:
        code, name = extract_code_and_name(url)
        with requests.Session() as session:
            saved = download_images_for_page(session, url, image_folder, code, name)
        return (url, saved, None)
    except Exception as e:
        logger.error("worker 异常: %s -> %s", url, e)
        return (url, 0, str(e))


def download_barbour_images_multi(max_workers=6):
    links_file = BARBOUR["LINKS_FILE"]
    image_folder = BARBOUR["IMAGE_DOWNLOAD"]

    logger.info("配置: LINKS_FILE=%s", links_file)
    logger.info("配置: IMAGE_DOWNLOAD=%s", image_folder)

    if not os.path.exists(links_file):
        logger.error("链接文件不存在: %s", links_file)
        return

    os.makedirs(image_folder, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        logger.warning("链接文件为空: %s", links_file)
        return

    logger.info("共 %d 个商品链接，开启 %d 线程并发下载...", len(urls), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(worker, url, image_folder): url for url in urls}

        for fut in as_completed(futures):
            url = futures[fut]
            try:
                _, saved, err = fut.result()
                if err:
                    logger.error("失败: %s 错误: %s", url, err)
                else:
                    logger.info("完成: %s  下载 %d 张", url, saved)
            except Exception as e:
                logger.error("异常线程: %s -> %s", url, e)

    logger.info("并发下载全部完成！")


# ========== 单线程入口（保留兼容） ==========
def download_barbour_images():
    links_file = BARBOUR["LINKS_FILE"]
    image_folder = BARBOUR["IMAGE_DOWNLOAD"]

    logger.info("配置: LINKS_FILE=%s", links_file)
    logger.info("配置: IMAGE_DOWNLOAD=%s", image_folder)

    if not os.path.exists(links_file):
        logger.error("链接文件不存在: %s", links_file)
        return

    os.makedirs(image_folder, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        logger.warning("链接文件为空: %s", links_file)
        return

    logger.info("共 %d 个商品链接，开始依次下载...", len(urls))

    with requests.Session() as session:
        for idx, url in enumerate(urls, 1):
            try:
                code, name = extract_code_and_name(url)
                saved = download_images_for_page(session, url, image_folder, code, name)
                logger.info("[%d/%d] %s 下载张数: %d", idx, len(urls), url, saved)
            except Exception as e:
                logger.error("[%d/%d] 失败: %s, 错误: %s", idx, len(urls), url, e)

    logger.info("所有图片处理完毕。")


# ========== 命令行入口 ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Barbour 商品图片下载器")
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数 (默认 6)")
    parser.add_argument("--single", action="store_true", help="使用单线程模式")
    args = parser.parse_args()

    setup_logging(debug=args.debug)

    logger.info("========== Barbour 图片下载 启动 ==========")
    logger.info("LINKS_FILE = %s", BARBOUR.get("LINKS_FILE", "未配置"))
    logger.info("IMAGE_DOWNLOAD = %s", BARBOUR.get("IMAGE_DOWNLOAD", "未配置"))

    if args.single:
        download_barbour_images()
    else:
        download_barbour_images_multi(max_workers=args.workers)
