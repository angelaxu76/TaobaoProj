"""
generate_empty_product_links_for_brand.py

通用脚本：适用于所有品牌（camper, clarks, ecco, geox, barbour, reiss, marksandspencer ...）

背景：
fetch_info 抓取时偶尔会因为网络问题（超时/被拦截等）写出"空壳" TXT ——
价格字段和库存字段全部为空/为 0，但文件本身确实存在（不属于 generate_missing_links_for_brand
处理的"TXT 中完全缺失"的情况）。这些商品需要用 Source URL 重新抓一次。

功能：
1. 扫描指定品牌 TXT_DIR 下所有商品 TXT 文件。
2. 判断该商品是否"价格 + 库存全部为空"。
3. 收集这些商品的 Source URL，写入一个 links 文件，供该品牌的 fetch_info 函数重新抓取。

前置约定（与 common/ingest/txt_writer.py 保持一致，所有品牌统一）：
- TXT 为 "Key: Value" 格式，每行一个字段。
- 价格字段：Product Price / Adjusted Price
- 库存字段：Product Size（SIZE:状态;...） / Product Size Detail（SIZE:库存:EAN;...）
- 来源字段：Source URL

用法（以 camper 为例）：
    from channels.jingya.maintenance.generate_empty_product_links_for_brand import generate_empty_product_links_for_brand
    from brands.camper.fetch_product_info import camper_fetch_product_info

    empty_links_file = generate_empty_product_links_for_brand("camper")
    if empty_links_file.exists() and empty_links_file.stat().st_size > 0:
        camper_fetch_product_info(links_file=str(empty_links_file))
"""

from pathlib import Path
from typing import Dict, List
import argparse

from config import BRAND_CONFIG
from common.utils.txt_parser import extract_product_info

# 视为"无价格"的占位值
_EMPTY_PRICE_VALUES = {"", "0", "0.0", "0.00"}


def _is_price_empty(info: Dict[str, str]) -> bool:
    for key in ("Product Price", "Adjusted Price"):
        val = (info.get(key) or "").strip()
        if val not in _EMPTY_PRICE_VALUES:
            return False
    return True


def _has_stock(info: Dict[str, str]) -> bool:
    # 1) 优先看 Product Size Detail: "SIZE:stock:EAN;..."（stock 为数字时判断 > 0）
    detail = (info.get("Product Size Detail") or "").strip()
    for token in detail.split(";"):
        token = token.strip()
        if not token:
            continue
        parts = token.split(":")
        if len(parts) >= 2:
            try:
                if int(parts[1]) > 0:
                    return True
            except ValueError:
                pass  # 非数字库存写法（如 barbour 的 text 模式），交给下面的 Product Size 判断

    # 2) 兜底看 Product Size: "SIZE:有货/无货;..."
    size_map = (info.get("Product Size") or "").strip()
    for token in size_map.split(";"):
        token = token.strip()
        if not token:
            continue
        parts = token.split(":")
        if len(parts) >= 2 and parts[1].strip() == "有货":
            return True

    return False


def is_empty_product_info(info: Dict[str, str]) -> bool:
    """价格和库存是否同时全空（典型的网络失败空壳 TXT）"""
    if not info:
        return True
    return _is_price_empty(info) and not _has_stock(info)


def generate_empty_product_links_for_brand(brand: str,
                                            output_filename: str = "empty_product_links.txt") -> Path:
    """
    为指定品牌生成"价格+库存全空"的商品链接文件。
    output_filename 可以是:
        1) 仅文件名  → 自动写到 brand/publication/ 下
        2) 完整路径（绝对路径/相对路径） → 直接按此路径写入
    无论是否找到结果都会写文件（找不到则写空文件），避免遗留上一次运行的旧内容。
    """
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知 brand：{brand}，请检查 BRAND_CONFIG 中是否已配置。")

    cfg = BRAND_CONFIG[brand]
    base_dir = Path(cfg["BASE"])
    txt_dir = Path(cfg["TXT_DIR"])

    publication_dir = base_dir / "publication"
    publication_dir.mkdir(parents=True, exist_ok=True)

    output_path = Path(output_filename)
    empty_links_file = output_path if output_path.is_absolute() else publication_dir / output_filename
    empty_links_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n🧩 处理品牌：{brand}")
    print(f"📁 TXT 目录：{txt_dir}")
    print(f"📂 输出文件：{empty_links_file}")

    if not txt_dir.exists():
        print(f"⚠️ TXT 目录不存在：{txt_dir}")
        empty_links_file.write_text("", encoding="utf-8")
        return empty_links_file

    empty_urls: List[str] = []
    no_url_codes: List[str] = []
    total = 0

    for txt_file in txt_dir.glob("*.txt"):
        total += 1
        info = extract_product_info(txt_file)
        if not is_empty_product_info(info):
            continue
        url = (info.get("Source URL") or "").strip()
        if url:
            empty_urls.append(url)
        else:
            no_url_codes.append(txt_file.stem)

    empty_urls = sorted(set(empty_urls))
    empty_links_file.write_text("\n".join(empty_urls), encoding="utf-8")

    print(f"📊 数据概览：TXT 总数={total}，价格/库存全空={len(empty_urls) + len(no_url_codes)}，"
          f"可重新抓取(有URL)={len(empty_urls)}")
    if no_url_codes:
        preview = no_url_codes[:10]
        suffix = " ..." if len(no_url_codes) > 10 else ""
        print(f"⚠️ 以下 {len(no_url_codes)} 个商品缺少 Source URL，无法自动重抓：{preview}{suffix}")

    if empty_urls:
        print(f"💾 已写入 {len(empty_urls)} 条空数据商品链接到：{empty_links_file}")
        print("📝 示例 URL（最多5条）：")
        for u in empty_urls[:5]:
            print("   ", u)
    else:
        print("🎉 没有发现价格/库存全空的商品。")

    return empty_links_file


def main():
    parser = argparse.ArgumentParser(
        description="扫描指定品牌 TXT 目录，找出价格+库存全空的商品，输出可重新抓取的链接文件。"
    )
    parser.add_argument(
        "brand",
        help="品牌名称，例如：camper / clarks / ecco / geox"
    )
    parser.add_argument(
        "--output",
        default="empty_product_links.txt",
        help="输出的 links 文件名（默认：empty_product_links.txt）"
    )

    args = parser.parse_args()
    generate_empty_product_links_for_brand(args.brand, args.output)


if __name__ == "__main__":
    main()
