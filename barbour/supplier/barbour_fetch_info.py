# barbour_fetch_info.py
# -*- coding: utf-8 -*-

import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

from config import BARBOUR
from common_taobao.txt_writer import format_txt              # ✅ 统一写入模板
from barbour.core.site_utils import assert_site_or_raise as canon


# 可选：更稳的 Barbour 性别兜底（M*/L* 前缀）
try:
    from common_taobao.core.size_normalizer import infer_gender_for_barbour
except Exception:
    infer_gender_for_barbour = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CANON_SITE = canon("barbour")

# ---------- 尺码标准化（与其它站点一致） ----------
WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（按你的要求：不含 52）

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS",  "XS":  "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def _extract_gender_from_html(html: str) -> str:
    """
    从页面的数据层里读出性别标签，落到：男款/女款/童款/未知
    """
    m = re.search(r'"item_category"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    gender_raw = m.group(1).strip().lower() if m else ""
    mapping = {
        "womens": "女款", "women": "女款", "ladies": "女款",
        "mens": "男款",   "men": "男款",
        "kids": "童款", "children": "童款", "child": "童款",
        "unisex": "中性",
    }
    return mapping.get(gender_raw, "未知")

def _extract_material_from_features(features_text: str) -> str:
    if not features_text:
        return "No Data"
    text = features_text.replace("\n", " ").replace("\r", " ")
    mats = re.findall(r"\b\d{1,3}%\s+[A-Za-z][A-Za-z \-]*", text)
    if mats:
        return " / ".join(mats[:2])
    return "No Data"

def _normalize_size_token(token: str, gender: str) -> str | None:
    s = (token or "").strip().upper()
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)
    s = re.sub(r"\s+", " ", s)

    # 先数字
    nums = re.findall(r"\d{1,3}", s)
    if nums:
        n = int(nums[0])
        if gender == "女款" and n in {4,6,8,10,12,14,16,18,20}:
            return str(n)
        if gender == "男款":
            # 男数字 30..50（偶数），明确排除 52
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)
            # 就近容错：28..54 → 贴近偶数并裁剪到 30..50
            if 28 <= n <= 54:
                cand = n if n % 2 == 0 else n - 1
                cand = max(30, min(50, cand))
                return str(cand)
        return None

    # 再字母
    key = s.replace("-", "").replace(" ", "")
    return ALPHA_MAP.get(key)

def _sort_sizes(keys: list[str], gender: str) -> list[str]:
    if gender == "女款":
        return [k for k in WOMEN_ORDER if k in keys]
    return [k for k in MEN_ALPHA_ORDER if k in keys] + [k for k in MEN_NUM_ORDER if k in keys]

def _build_size_lines_from_buttons(size_buttons_map: dict[str, str], gender: str) -> tuple[str, str]:
    """
    用按钮文本和可用性生成两行，并补齐未出现的尺码为无货(0)：
      - Product Size: "34:有货;36:无货;..."
      - Product Size Detail: "34:3:0000000000000;36:0:0000000000000;..."
    规则：
      - 同尺码重复出现时，“有货”优先
      - 男款：自动在【字母系(2XS–3XL)】与【数字系(30–50, 不含52)】二选一，绝不混用
      - 女款：固定 4–20
    """
    status_bucket: dict[str, str] = {}
    stock_bucket: dict[str, int] = {}

    # 1) 先把页面上“出现的尺码”写入（有货优先覆盖）
    for raw, status in (size_buttons_map or {}).items():
        norm = _normalize_size_token(raw, gender or "男款")
        if not norm:
            continue
        curr = "有货" if status == "有货" else "无货"
        prev = status_bucket.get(norm)
        if prev is None or (prev == "无货" and curr == "有货"):
            status_bucket[norm] = curr
            stock_bucket[norm] = 3 if curr == "有货" else 0

    # 2) 按性别选择“单一尺码系”的完整顺序表
    if (gender or "男款") == "女款":
        full_order = WOMEN_ORDER[:]  # 4..20
    else:
        # 男款：根据已出现的尺码自动判定使用哪一系（字母 或 数字）
        keys = set(status_bucket.keys())
        has_num   = any(k in MEN_NUM_ORDER   for k in keys)
        has_alpha = any(k in MEN_ALPHA_ORDER for k in keys)
        if has_num and not has_alpha:
            chosen = MEN_NUM_ORDER[:]        # 只用数字系 30..50
        elif has_alpha and not has_num:
            chosen = MEN_ALPHA_ORDER[:]      # 只用字母系 2XS..3XL
        elif has_num or has_alpha:
            # 同时出现（异常场景）：取出现数量多的那一系
            num_count   = sum(1 for k in keys if k in MEN_NUM_ORDER)
            alpha_count = sum(1 for k in keys if k in MEN_ALPHA_ORDER)
            chosen = MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]
            # 把另一系的键删掉，确保不混用
            for k in list(status_bucket.keys()):
                if k not in chosen:
                    status_bucket.pop(k, None)
                    stock_bucket.pop(k, None)
        else:
            # 页面啥也没识别到：默认用字母系（更常见的外套）
            chosen = MEN_ALPHA_ORDER[:]
        full_order = chosen

    # 3) 对“未出现”的尺码补齐为 无货/0（仅在选定的那一系内补齐）
    for s in full_order:
        if s not in status_bucket:
            status_bucket[s] = "无货"
            stock_bucket[s] = 0

    # 4) 固定顺序输出（只输出选定那一系）
    ordered = [s for s in full_order]
    ps  = ";".join(f"{k}:{status_bucket[k]}" for k in ordered)
    psd = ";".join(f"{k}:{stock_bucket[k]}:0000000000000" for k in ordered)
    return ps, psd



# ---------- 解析核心：保持你当前的结构 ----------
def extract_product_info_from_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # 名称 / SKU 从 ld+json 里拿（Barbour 官网常见）
    name = "No Data"
    sku = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        data = _safe_json_loads(script.string or "")
        if isinstance(data, dict) and data.get("@type") == "Product":
            if data.get("name"):
                name = str(data["name"]).strip()
            if data.get("sku"):
                sku = str(data["sku"]).strip()
            break

    # 描述
    desc_tag = soup.find("div", {"id": "collapsible-description-1"})
    description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else "No Data"
    if sku and sku != "No Data":
        description = description.replace(f"SKU: {sku}", "").strip() or "No Data"

    # Features（含保养/材质等）
    features_tag = soup.find("div", class_="care-information")
    features = features_tag.get_text(separator=" | ", strip=True) if features_tag else "No Data"

    # 价格
    price = "0"
    price_tag = soup.select_one("span.sales span.value")
    if price_tag and price_tag.has_attr("content"):
        price = price_tag["content"]

    # 颜色
    color_tag = soup.select_one("span.selected-color")
    color = color_tag.get_text(strip=True).replace("(", "").replace(")", "") if color_tag else "No Data"

    # 尺码按钮（有无货）
    size_buttons = soup.select("div.size-wrapper button.size-button")
    size_map = {}
    for btn in size_buttons or []:
        size_text = btn.get_text(strip=True)
        if not size_text:
            continue
        disabled = ("disabled" in (btn.get("class") or [])) or btn.has_attr("disabled")
        size_map[size_text] = "无货" if disabled else "有货"

    # 性别 / 主体材质
    product_gender = _extract_gender_from_html(html)
    product_material = _extract_material_from_features(features)

    # —— 从按钮直接构建两行（不写 SizeMap；并过滤 52）——
    ps, psd = _build_size_lines_from_buttons(size_map, product_gender)

    # 如可用，用 Barbour 前缀再次兜底性别
    if infer_gender_for_barbour:
        product_gender = infer_gender_for_barbour(
            product_code=sku,
            title=name,
            description=description,
            given_gender=product_gender,
        ) or product_gender or "男款"

    info = {
        "Product Code": sku,                 # ✅ 官网 SKU
        "Product Name": name,
        "Product Description": description,
        "Product Gender": product_gender,
        "Product Color": color,
        "Product Price": price,
        "Adjusted Price": price,             # 促销价与售价暂同
        "Product Material": product_material,
        "Feature": features,
        "Product Size": ps,                  # ✅ 直接两行
        "Product Size Detail": psd,
        # 不写 SizeMap（按你的统一规范）
        "Source URL": url,
        "Site Name": CANON_SITE,
        # 不传 Style Category → 交给 txt_writer 做统一推断
    }
    return info

# ---------- 主流程（保持函数名） ----------
def barbour_fetch_info():
    links_file = BARBOUR["LINKS_FILE"]
    txt_output_dir = Path(BARBOUR["TXT_DIR"])
    txt_output_dir.mkdir(parents=True, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"📄 共 {len(urls)} 个商品页面待解析...")

    for idx, url in enumerate(urls, 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            info = extract_product_info_from_html(resp.text, url)

            # 文件名：用 SKU（无则用安全化标题）
            code_for_file = info.get("Product Code") or re.sub(r"[^A-Za-z0-9\-]+", "_", info.get("Product Name", "NoCode"))
            txt_path = txt_output_dir / f"{code_for_file}.txt"

            # ✅ 统一写出（和其它站点完全一致）
            format_txt(info, txt_path, brand="Barbour")
            print(f"✅ [{idx}/{len(urls)}] 写入成功：{txt_path.name}")

        except Exception as e:
            print(f"❌ [{idx}/{len(urls)}] 失败：{url}，错误：{e}")

if __name__ == "__main__":
    barbour_fetch_info()
