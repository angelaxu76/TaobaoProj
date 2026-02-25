# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Dict, Any
from config import SETTINGS

# —— 仅 Barbour 分支会用到（Camper/Clarks 不触发）——
try:
    from common.product.size_utils import clean_size_for_barbour
except Exception:
    # 若你的工程路径不同，可用本地兜底
    def clean_size_for_barbour(s: str) -> str:
        return (s or "").strip()

def _is_barbour(info: Dict[str, Any], brand: str | None) -> bool:
    b = (brand or info.get("Brand") or "").strip().lower()
    if b == "barbour":
        return True
    # 站点名或特征兜底判断（不严）
    site = (info.get("Site Name") or "").lower()
    name = (info.get("Product Name") or "").lower()
    return any(k in site for k in [
        "outdoor and country", "allweathers", "philip morris", "country attire", "barbour"
    ]) or "barbour" in name

# —— 仅 Barbour 用：从 offers 回填价格（有货优先，否则取第一条）——
def _inject_price_from_offers(info: Dict[str, Any]) -> None:
    if info.get("Product Price"):
        return
    offers = info.get("Offers") or []
    price_val = None
    for size, price, stock_text, can_order in offers:
        if price:
            if can_order:
                price_val = price
                break
            if price_val is None:
                price_val = price
    if price_val:
        info["Product Price"] = str(price_val)

# —— 仅 Barbour 用：清洗两行尺码 ——
def _clean_sizes_for_barbour(info: Dict[str, Any]) -> None:
    # Product Size: "S:有货;M:无货..."
    if info.get("Product Size"):
        cleaned = []
        for token in str(info["Product Size"]).split(";"):
            if not token.strip():
                continue
            try:
                size, status = token.split(":")
                size = clean_size_for_barbour(size)
                cleaned.append(f"{size}:{status}")
            except ValueError:
                cleaned.append(token)
        info["Product Size"] = ";".join(cleaned)

    # Product Size Detail: "S:1:EAN;M:0:EAN..."
    if info.get("Product Size Detail"):
        cleaned = []
        for token in str(info["Product Size Detail"]).split(";"):
            if not token.strip():
                continue
            parts = token.split(":")
            if len(parts) == 3:
                size, stock, ean = parts
                size = clean_size_for_barbour(size)
                cleaned.append(f"{size}:{stock}:{ean}")
            else:
                cleaned.append(token)
        info["Product Size Detail"] = ";".join(cleaned)

# —— 仅 Barbour 用：若无 Detail，用 Size 兜底生成 ——


def _ensure_detail_from_size(info: Dict[str, Any]) -> None:
    if info.get("Product Size") and not info.get("Product Size Detail"):
        mode = SETTINGS.get("STOCK_VALUE_MODE", "binary")  # ← 全局控制
        default_count = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

        tokens = [t.strip() for t in str(info["Product Size"]).split(";") if t.strip()]
        detail = []

        for t in tokens:
            try:
                size, status = t.split(":")
                size = clean_size_for_barbour(size)
                status = status.strip()

                # --- 根据 config 自动决定库存写法 ---
                if mode == "binary":
                    stock = 1 if status == "有货" else 0

                elif mode == "text":
                    stock = status  # 直接写“有货/无货”

                elif mode == "count":
                    stock = default_count if status == "有货" else 0

                elif mode == "bool":
                    stock = "True" if status == "有货" else "False"

                elif mode == "raw":
                    stock = status  # 完全保持原样

                else:
                    stock = 1 if status == "有货" else 0  # fallback

                detail.append(f"{size}:{stock}:0000000000000")

            except ValueError:
                continue

        if detail:
            info["Product Size Detail"] = ";".join(detail)


def _write_line(lines: list[str], key: str, val):
    if val is not None and val != "":
        lines.append(f"{key}: {val}")

def _write_common_fields(lines: list[str], info: Dict[str, Any]) -> None:
    _write_line(lines, "Product Code", info.get("Product Code"))
    _write_line(lines, "Product Name", info.get("Product Name"))
    _write_line(lines, "Product Description", info.get("Product Description"))
    _write_line(lines, "Product Gender", info.get("Product Gender"))
    _write_line(lines, "Product Color", info.get("Product Color"))
    _write_line(lines, "Product Price", info.get("Product Price"))
    _write_line(lines, "Adjusted Price", info.get("Adjusted Price"))
    _write_line(lines, "Product Material", info.get("Product Material"))
    _write_line(lines, "Style Category", info.get("Style Category"))
    _write_line(lines, "Feature", info.get("Feature"))

def _write_sizes_for_legacy(lines: list[str], info: Dict[str, Any]) -> None:
    """
    旧版（Camper/Clarks）完全保持：
    - 优先 SizeMap 组 Product Size
    - 若有 SizeDetail(dict)：写 Product Size Detail: size:stock:ean
    - 不做任何清洗/推断
    """
    if "SizeMap" in info and isinstance(info["SizeMap"], dict):
        size_str = ";".join(f"{size}:{status}" for size, status in info["SizeMap"].items())
        lines.append(f"Product Size: {size_str}")
    elif "Product Size" in info:
        lines.append(f"Product Size: {info['Product Size']}")

    if "SizeDetail" in info and isinstance(info["SizeDetail"], dict):
        detail_lines = []
        for size, detail in info["SizeDetail"].items():
            stock_count = detail.get("stock_count", 0)
            ean = detail.get("ean", "")
            detail_lines.append(f"{size}:{stock_count}:{ean}")
        if detail_lines:
            lines.append("Product Size Detail: " + ";".join(detail_lines))

def _write_sizes_for_barbour(lines: list[str], info: Dict[str, Any]) -> None:
    """
    Barbour 分支：
    - 先做价格回填与尺码清洗
    - Product Size 若存在直接写
    - Product Size Detail：优先已有；否则从 Product Size 兜底生成
    """
    # 尺码/价格处理
    _inject_price_from_offers(info)
    _clean_sizes_for_barbour(info)
    _ensure_detail_from_size(info)

    # 写出
    if "Product Size" in info and info["Product Size"]:
        _write_line(lines, "Product Size", info["Product Size"])
    if "Product Size Detail" in info and info["Product Size Detail"]:
        _write_line(lines, "Product Size Detail", info["Product Size Detail"])

def format_txt(info: dict, filepath: Path, brand: str = None):
    """
    统一写入入口（方法签名不变）
    - 对 Camper/Clarks：完全按你旧版写法输出（不做清洗、无副作用）
    - 对 Barbour：仅此分支做“从 offers 回填价格 + 尺码清洗 + Detail 兜底”
    """
    lines: list[str] = []

    # 基础字段（所有品牌一致）
    _write_common_fields(lines, info)

    # —— 尺码部分：按品牌分支 ——
    if _is_barbour(info, brand):
        _write_sizes_for_barbour(lines, info)
    else:
        _write_sizes_for_legacy(lines, info)

    # 站点/来源字段（所有品牌一致）
    _write_line(lines, "Site Name", info.get("Site Name"))
    _write_line(lines, "Source URL", info.get("Source URL"))

    # 写文件
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入 TXT: {filepath.name}")
