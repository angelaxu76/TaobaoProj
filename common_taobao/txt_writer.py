from pathlib import Path
from typing import Dict, Any

from common_taobao.core.category_utils import infer_style_category
from common_taobao.core.size_normalizer import infer_gender_for_barbour


def _safe_infer_category(info: Dict[str, Any], brand: str | None) -> str:
    """
    安全调用分类器：
    1) 先尝试新版签名(desc, product_name, product_code, brand)
    2) 若抛 TypeError，退回旧签名 infer_style_category(desc)
    """
    desc = info.get("Product Description", "") or ""
    name = info.get("Product Name", "") or ""
    code = info.get("Product Code", "") or ""
    b = (brand or info.get("Brand") or "") or ""
    try:
        return infer_style_category(
            desc=desc, product_name=name, product_code=code, brand=b
        )
    except TypeError:
        return infer_style_category(desc=desc)  # 兼容旧函数定义


def _ensure_size_detail_from_size(info: Dict[str, Any]) -> None:
    """
    若只有 Product Size，没有 Product Size Detail，则按 有货=1 / 无货=0 + 占位 EAN 生成 Detail。
    """
    if info.get("Product Size") and not info.get("Product Size Detail"):
        tokens = [t.strip() for t in str(info["Product Size"]).split(";") if t.strip()]
        detail = []
        for t in tokens:
            try:
                size, status = t.split(":")
                stock = 1 if status == "有货" else 0
                detail.append(f"{size}:{stock}:0000000000000")
            except ValueError:
                continue
        if detail:
            info["Product Size Detail"] = ";".join(detail)


def format_txt(info: dict, filepath: Path, brand: str = None):
    """
    统一写入 TXT（与其它站点一致）
    - 写出 Site Name、Source URL
    - Product Size Detail 兼容字符串/字典/自动兜底三种来源
    - 不强制输出 SizeMap（你已不需要）
    - 类目推断做新旧签名兼容
    - Barbour 性别兜底
    """
    # ✅ 性别兜底（仅 Barbour）
    if (brand or info.get("Brand")) == "Barbour":
        info["Product Gender"] = infer_gender_for_barbour(
            product_code=info.get("Product Code"),
            title=info.get("Product Name"),
            description=info.get("Product Description"),
            given_gender=info.get("Product Gender"),
        ) or info.get("Product Gender") or "男款"

    # ✅ 类目智能化（安全调用）
    if not info.get("Style Category"):
        info["Style Category"] = _safe_infer_category(info, brand)

    lines: list[str] = []

    def write_line(key: str, val):
        if val is not None and val != "":
            lines.append(f"{key}: {val}")

    # ===== 基础字段 =====
    write_line("Product Code", info.get("Product Code"))
    write_line("Product Name", info.get("Product Name"))
    write_line("Product Description", info.get("Product Description"))
    write_line("Product Gender", info.get("Product Gender"))
    write_line("Product Color", info.get("Product Color"))
    write_line("Product Price", info.get("Product Price"))          # 可选
    write_line("Adjusted Price", info.get("Adjusted Price"))        # 可选
    write_line("Product Material", info.get("Product Material"))    # 可选
    write_line("Style Category", info.get("Style Category"))
    write_line("Feature", info.get("Feature"))

    # ===== 尺码（不再单独输出 SizeMap）=====
    if "Product Size" in info:
        write_line("Product Size", info.get("Product Size"))
    elif "SizeMap" in info:  # 兼容旧上游：用 SizeMap 组装 Product Size
        size_str = ";".join(f"{size}:{status}" for size, status in info["SizeMap"].items())
        write_line("Product Size", size_str)

    # Product Size Detail：优先字符串；其次从 SizeDetail(dict) 生成；最后自动兜底
    if info.get("Product Size Detail"):
        write_line("Product Size Detail", info["Product Size Detail"])
    elif "SizeDetail" in info and isinstance(info["SizeDetail"], dict):
        detail_lines = []
        for size, detail in info["SizeDetail"].items():
            stock_count = detail.get("stock_count", 0)
            ean = detail.get("ean", "0000000000000")
            detail_lines.append(f"{size}:{stock_count}:{ean}")
        if detail_lines:
            lines.append("Product Size Detail: " + ";".join(detail_lines))
    else:
        _ensure_size_detail_from_size(info)
        write_line("Product Size Detail", info.get("Product Size Detail"))

    # ===== 站点与来源 =====
    write_line("Site Name", info.get("Site Name"))     # ✅ 新增：写出站点名
    write_line("Source URL", info.get("Source URL"))

    # ===== 写文件 =====
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入 TXT: {filepath.name}")
