import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ✅ 加入项目根目录
sys.path.append(str(Path(__file__).resolve().parents[2]))

from config import CLARKS
from common.ingest.txt_writer import format_txt
from brands.clarks.fetch_product_info import process_product, LINK_FILE

TXT_DIR = CLARKS["TXT_DIR"]
BRAND = CLARKS["BRAND"]
EBAY_NAMES_FILE = CLARKS["BASE"] / "publication" / "ebay_product_names.txt"

# outlet 商品链接域名标记，www.clarks.com 的链接不处理
OUTLET_URL_MARKER = "clarksoutlet"


def normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def load_ebay_word_sets(ebay_file=None) -> list[set[str]]:
    ebay_file = ebay_file or EBAY_NAMES_FILE
    with open(ebay_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return [set(normalize_words(line)) for line in lines]


def split_links_by_source(links_file=None):
    """
    读取 product_links.txt，按域名拆分成常规链接（www.clarks.com）和 outlet 链接。
    返回 (regular_urls, outlet_urls)。
    """
    links_file = links_file or LINK_FILE
    with open(links_file, "r", encoding="utf-8") as f:
        all_urls = [line.strip() for line in f if line.strip()]

    outlet_urls = [u for u in all_urls if OUTLET_URL_MARKER in u]
    regular_urls = [u for u in all_urls if OUTLET_URL_MARKER not in u]
    return regular_urls, outlet_urls


def write_regular_links_file(links_file=None, output_file=None) -> Path:
    """
    从 product_links.txt 中过滤出非 outlet（www.clarks.com）链接，单独写一份文件，
    供 clarks_fetch_info()（v1，全量不过滤）只处理常规商品使用，避免重复处理 outlet 商品。
    """
    regular_urls, _ = split_links_by_source(links_file)

    if output_file is None:
        output_file = CLARKS["BASE"] / "publication" / "product_links_regular.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for url in regular_urls:
            f.write(url.strip() + "\n")

    print(f"✅ 常规商品链接 {len(regular_urls)} 条已写入: {output_file}")
    return output_file


def match_ebay_name(product_name: str, ebay_word_sets: list) -> bool:
    """
    匹配规则：fetch info 商品名称共 n 个词，其中 n-1 个词能在 ebay 某条记录的词集合中找到即算匹配。
    n=1 时至少要求这 1 个词命中，避免单词标题无条件通过。
    """
    words = normalize_words(product_name)
    n = len(words)
    if n == 0:
        return False
    threshold = max(1, n - 1)

    for ebay_words in ebay_word_sets:
        matched = sum(1 for w in words if w in ebay_words)
        if matched >= threshold:
            return True
    return False


def clarks_outlet_fetch_info_v2(links_file=None, ebay_file=None):
    """
    Clarks Outlet 商品抓取入口 v2：
    - 只处理 clarksoutlet.co.uk 的商品链接（www.clarks.com 的跳过不处理）
    - eBay 过滤已屏蔽，抓取到的商品全部写入 txt（不再按 ebay_product_names.txt 过滤）

    返回 (matched_count, skipped_count) 供调用方汇总统计。
    """
    if links_file is None:
        links_file = LINK_FILE
    if ebay_file is None:
        ebay_file = EBAY_NAMES_FILE

    print(f"📄 使用链接文件: {links_file}")
    print(f"📄 使用 eBay 商品名称文件: {ebay_file}")

    regular_urls, outlet_urls = split_links_by_source(links_file)
    print(f"🔎 共 {len(regular_urls) + len(outlet_urls)} 条链接，其中 outlet 链接 {len(outlet_urls)} 条")

    # 🔒 eBay 过滤已屏蔽，如需恢复取消下面这行注释
    # ebay_word_sets = load_ebay_word_sets(ebay_file)
    ebay_word_sets = []
    print(f"🔎 已加载 eBay 商品名称 {len(ebay_word_sets)} 条（eBay 过滤已屏蔽）")

    matched_count = 0
    skipped_count = 0

    for url in outlet_urls:
        info = process_product(url)
        if not info:
            continue

        product_name = info["Product Name"]

        # 🔒 eBay 过滤已屏蔽，如需恢复取消下面这段注释
        # if not match_ebay_name(product_name, ebay_word_sets):
        #     print(f"⏭️ 未在 eBay 商品名称中找到匹配，跳过: {product_name}")
        #     skipped_count += 1
        #     continue

        matched_count += 1
        print(f"\n🔍 {url}")
        for k, v in info.items():
            print(f"{k}: {v}")

        filepath = TXT_DIR / f"{info['Product Code']}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        format_txt(info, filepath, BRAND)
        print(f"✅ 写入: {filepath.name}")

    print(f"\n✅ 完成：匹配写入 {matched_count} 条，跳过 {skipped_count} 条")

    return matched_count, skipped_count


if __name__ == "__main__":
    clarks_outlet_fetch_info_v2()
