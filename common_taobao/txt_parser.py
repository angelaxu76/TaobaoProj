# -*- coding: utf-8 -*-
from typing import List, Tuple
from pathlib import Path

MIN_STOCK_THRESHOLD = 1  # 小于该值视为 0（仅 Barbour/jingya 解析用）

def parse_txt_to_record(filepath: Path, brand: str) -> List[Tuple]:
    b = (brand or "").lower()
    if b in {"camper", "clarks_jingya", "clarks"}:
        return parse_camper_or_generic(filepath)  # 旧逻辑保持
    elif b in {"barbour"}:
        return parse_barbour_jingya(filepath)     # Barbour 解析 Size Detail
    else:
        return parse_generic_txt(filepath)        # 兜底

# ===== 旧逻辑：与你上传的 txtparse.txt 完全一致的两套 =====
def parse_generic_txt(filepath: Path) -> List[Tuple]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    product_code = product_name = product_desc = gender = color = ""
    original_price = discount_price = material = sizes_line = url = ""
    feature = ""

    for line in lines:
        line = line.strip()
        if line.startswith("Product Code:"):
            product_code = line.split(":", 1)[1].strip()
        elif line.startswith("Product Name:"):
            product_name = line.split(":", 1)[1].strip()
        elif line.startswith("Product Description:"):
            product_desc = line.split(":", 1)[1].strip()
        elif line.startswith("Product Gender:"):
            gender = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color:"):
            color = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            original_price = line.split(":", 1)[1].strip().replace("£", "").strip()
        elif line.startswith("Adjusted Price:"):
            discount_price = line.split(":", 1)[1].strip()
        elif line.startswith("Product Material:"):
            material = line.split(":", 1)[1].strip()
        elif line.startswith("Feature:"):
            feature = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size:"):
            sizes_line = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:"):
            url = line.split(":", 1)[1].strip()

    for size_info in sizes_line.split(";"):
        if not size_info.strip():
            continue
        size, status = size_info.split(":")
        size = size.strip()
        status = status.strip()
        records.append((
            product_code, url, size, gender, "",              # 第5位占位
            "有货" if "有货" in status else "无货",
            original_price, discount_price, "",               # 第9位占位
        ))
    return records

def parse_camper_or_generic(filepath: Path) -> List[Tuple]:
    """
    Camper/Clarks 版：保持你上传的旧逻辑（Product Size + 可选 Product Size Detail 里的 EAN）
    """
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    product_code = product_name = product_desc = gender = color = ""
    original_price = discount_price = material = sizes_line = url = ""
    feature = ""
    ean_line = ""

    for line in lines:
        line = line.strip()
        if line.startswith("Product Code:"):
            product_code = line.split(":", 1)[1].strip()
        elif line.startswith("Product Name:"):
            product_name = line.split(":", 1)[1].strip()
        elif line.startswith("Product Description:"):
            product_desc = line.split(":", 1)[1].strip()
        elif line.startswith("Product Gender:"):
            gender = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color:"):
            color = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            original_price = line.split(":", 1)[1].strip().replace("£", "").strip()
        elif line.startswith("Adjusted Price:"):
            discount_price = line.split(":", 1)[1].strip()
        elif line.startswith("Product Material:"):
            material = line.split(":", 1)[1].strip()
        elif line.startswith("Feature:"):
            feature = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size:"):
            sizes_line = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size Detail:"):
            ean_line = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:"):
            url = line.split(":", 1)[1].strip()

    if not url:
        print(f"❌ 缺失 product_url，跳过编码: {product_code}")
        return []

    # 解析 EAN 映射（可为空）
    ean_dict = {}
    for ean_info in ean_line.split(";"):
        if not ean_info.strip():
            continue
        try:
            size, _, ean = ean_info.split(":")
            ean_dict[size.strip()] = ean.strip()
        except ValueError:
            continue

    for size_info in sizes_line.split(";"):
        if not size_info.strip():
            continue
        try:
            size, status = size_info.split(":")
            size = size.strip()
            status = status.strip()
            stock_status = "有货" if "有货" in status else "无货"
            ean = ean_dict.get(size, "")
            records.append((
                product_code, url, size, gender, "", stock_status,
                original_price, discount_price, "", ean
            ))
        except ValueError:
            continue

    return records

# ===== Barbour 版：优先解析 Size Detail（带库存数），无则回退到通用版 =====
def parse_barbour_jingya(filepath: Path) -> List[Tuple]:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {
        "product_code": "", "product_url": "", "gender": "",
        "original_price_gbp": "0", "discount_price_gbp": "0",
    }
    size_detail_map = {}
    sizes_line = ""

    for line in lines:
        s = line.strip()
        if s.startswith("Product Code:"):
            info["product_code"] = s.split(":", 1)[1].strip()
        elif s.startswith("Source URL:") or s.startswith("Product URL:"):
            info["product_url"] = s.split(":", 1)[1].strip()
        elif s.startswith("Product Gender:"):
            info["gender"] = s.split(":", 1)[1].strip()
        elif s.startswith("Product Price:"):
            info["original_price_gbp"] = s.split(":", 1)[1].strip().replace("£","").strip()
        elif s.startswith("Adjusted Price:"):
            info["discount_price_gbp"] = s.split(":", 1)[1].strip()
        elif s.startswith("Product Size Detail:"):
            raw = s.split(":", 1)[1]
            for item in raw.split(";"):
                parts = item.strip().split(":")
                if len(parts) == 3:
                    size, stock_count, ean = parts
                    try:
                        stock_count = int(stock_count)
                    except:
                        stock_count = 0
                    if stock_count < MIN_STOCK_THRESHOLD:
                        stock_count = 0
                    size_detail_map[size] = {"stock_count": stock_count, "ean": ean}
        elif s.startswith("Product Size:"):
            sizes_line = s.split(":", 1)[1].strip()

    # 优先用 Size Detail（有库存数字）
    if size_detail_map:
        recs = []
        for size, d in size_detail_map.items():
            recs.append((
                info["product_code"], info["product_url"], size, info["gender"],
                d["ean"], d["stock_count"], info["original_price_gbp"], info["discount_price_gbp"], False
            ))
        return recs

    # 回退：用通用版（仅 有货/无货）
    return parse_generic_txt(filepath)
