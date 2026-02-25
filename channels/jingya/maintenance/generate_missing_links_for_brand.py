"""
generate_missing_links_for_brand.py

通用脚本：用于四大鞋品牌（camper, clarks_jingya, ecco, geox）

功能：
1. 读取品牌 TXT 目录中的商品编码集合（文件名 = 编码）。
2. 从数据库表中读取所有商品编码 + product_url。
3. 找出“数据库仍存在，但 TXT 中缺失”的商品编码集合。
4. 将这些编码对应的 product_url 写入 missing product links 文件，供 fetch_info 再抓一次。

前置约定：
- config.BRAND_CONFIG[brand] 中包含：
    - "BASE"      → 品牌根目录，如 D:/TB/Products/camper 或 .../clarks_jingya
    - "TXT_DIR"   → 当前品牌 TXT 目录
    - "TABLE_NAME" → 数据库表名，如 "camper_inventory"
    - "PGSQL_CONFIG" → 数据库连接参数 dict(host, port, user, password, dbname)
- 数据库表中：
    - product_name 字段存放商品编码（已约定）
    - product_url  字段存放商品详情页链接
"""

from pathlib import Path
from typing import Dict, Set
import argparse

import psycopg2
from psycopg2.extras import DictCursor

from config import BRAND_CONFIG  # 请确认你已有这个结构，没有的话稍微改一下即可


def load_codes_from_txt_dir(txt_dir: Path) -> Set[str]:
    """
    从 TXT 目录读取商品编码集合（文件名去掉后缀），全部转为大写。
    """
    codes: Set[str] = set()
    if not txt_dir.exists():
        print(f"⚠️ TXT 目录不存在：{txt_dir}")
        return codes

    for txt_file in txt_dir.glob("*.txt"):
        code = txt_file.stem.strip()
        if code:
            codes.add(code.upper())

    print(f"✅ TXT 目录 {txt_dir} 中发现 {len(codes)} 个商品编码")
    return codes


from psycopg2.extras import DictCursor
from psycopg2.errors import UndefinedColumn   # 新增这一行

def load_codes_and_urls_from_db(table: str, db_conf: Dict) -> Dict[str, str]:
    """
    从数据库中读取所有商品编码 + 对应 product_url。
    ✅ 优先使用 product_code（你当前的实际字段）
    ✅ 如果没有 product_code 字段，再回退使用 product_name（兼容旧表 / 其他表）

    返回 dict: {CODE_UPPER: url}
    """
    # 先按你现在的标准：product_code
    sql_use_product_code = f"""
        SELECT DISTINCT product_code AS code, product_url
        FROM {table}
        WHERE product_url IS NOT NULL
    """
    # 兼容旧字段 / 其他表
    sql_use_product_name = f"""
        SELECT DISTINCT product_name AS code, product_url
        FROM {table}
        WHERE product_url IS NOT NULL
    """

    mapping: Dict[str, str] = {}

    print(f"🔌 正在连接数据库：{db_conf.get('host')} / {db_conf.get('dbname')}，读取 {table} ...")
    with psycopg2.connect(**db_conf) as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            try:
                # 1️⃣ 先用 product_code（你现在真实在用的列名）
                cur.execute(sql_use_product_code)
                print("✅ 使用字段 product_code 读取编码")
            except UndefinedColumn:
                # 2️⃣ 某些表可能还是 product_name，做个兜底
                print("⚠️ 当前表不存在字段 product_code，改用 product_name 读取编码")
                cur.execute(sql_use_product_name)

            rows = cur.fetchall()
            for row in rows:
                code = (row["code"] or "").strip()
                url = (row["product_url"] or "").strip()
                if code and url:
                    mapping.setdefault(code.upper(), url)

    print(f"✅ 数据库中读取到 {len(mapping)} 个带 URL 的商品编码")
    return mapping


def generate_missing_links_for_brand(brand: str,
                                     output_filename: str = "product_links_missing.txt") -> Path:
    """
    为指定品牌生成缺失商品链接文件。
    output_filename 可以是:
        1) 仅文件名  → 自动写到 brand/publication/ 下
        2) 完整路径（绝对路径/相对路径） → 直接按此路径写入
    """
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知 brand：{brand}，请检查 BRAND_CONFIG 中是否已配置。")

    cfg = BRAND_CONFIG[brand]
    base_dir = Path(cfg["BASE"])
    txt_dir = Path(cfg["TXT_DIR"])
    table = cfg["TABLE_NAME"]
    db_conf = cfg["PGSQL_CONFIG"]

    # publication 目录
    publication_dir = base_dir / "publication"
    publication_dir.mkdir(parents=True, exist_ok=True)

    # ============================
    # 🔥 关键增强：判断 output_filename 是否是路径
    # ============================
    output_path = Path(output_filename)
    if not output_path.is_absolute():
        # 不是绝对路径 → 视为文件名，放到 publication 下
        missing_links_file = publication_dir / output_filename
    else:
        # 是绝对路径 → 完全按照用户提供的写
        missing_links_file = output_path
    # ============================

    print(f"\n🧩 处理品牌：{brand}")
    print(f"📁 TXT 目录：{txt_dir}")
    print(f"📂 输出文件：{missing_links_file}")

    # 1) TXT 目录读取编码集合
    txt_codes = load_codes_from_txt_dir(txt_dir)

    # 2) DB 读取编码 + URL
    db_code_url = load_codes_and_urls_from_db(table, db_conf)
    db_codes = set(db_code_url.keys())

    # 3) DB 中存在但 TXT 缺失的
    missing_codes = sorted(db_codes - txt_codes)

    print(
        f"📊 数据概览：DB={len(db_codes)}，TXT={len(txt_codes)}，"
        f"缺失(仅存在于DB)={len(missing_codes)}"
    )

    if not missing_codes:
        print("🎉 没有缺失商品编码。")
        # 如果你想仍然生成空文件，可以取消注释：
        # missing_links_file.write_text("", encoding="utf-8")
        return missing_links_file

    # 4) 写入 URL 列表
    missing_urls = [db_code_url[c] for c in missing_codes if c in db_code_url]
    missing_urls = sorted(set(missing_urls))

    # 确保父目录存在
    missing_links_file.parent.mkdir(parents=True, exist_ok=True)
    missing_links_file.write_text("\n".join(missing_urls), encoding="utf-8")

    print(f"💾 已写入 {len(missing_urls)} 条缺失链接到：{missing_links_file}")
    print("📝 示例 URL（最多5条）：")
    for u in missing_urls[:5]:
        print("   ", u)

    return missing_links_file



def main():
    parser = argparse.ArgumentParser(
        description="为指定品牌生成缺失商品链接文件，用于 fetch_info 补抓。"
    )
    parser.add_argument(
        "brand",
        help="品牌名称，例如：camper / clarks_jingya / ecco / geox"
    )
    parser.add_argument(
        "--output",
        default="product_links_missing.txt",
        help="输出的 missing links 文件名（默认：product_links_missing.txt）"
    )

    args = parser.parse_args()
    generate_missing_links_for_brand(args.brand, args.output)


if __name__ == "__main__":
    main()
