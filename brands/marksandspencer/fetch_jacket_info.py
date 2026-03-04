# -*- coding: utf-8 -*-
# MS 服装（外套/针织/上衣/连衣裙等）统一解析脚本
# 使用 Selenium + __NEXT_DATA__ 解析全量信息
# 使用 format_txt 写入鲸芽标准格式 TXT
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from attr import attrs
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import MARKSANDSPENCER
from common.browser.selenium_utils import get_driver
from common.ingest.txt_writer import format_txt
from common.product.style_category_normalizer import normalize_style_category


CANON_SITE = "Marks & Spencer"


# ===================== 工具函数 =====================
def _apply_size_range_completion(size_map: dict, detail: dict, gender: str | None):
    """
    根据性别和现有尺码模式，补全尺码范围并自动补 0 库存：
    - 女款：
        * 若尺码不含数字（XS/S/M/L/XL） → 范围: XS-XL
        * 若尺码含数字（6/8/10/12 等） → 范围: 6-24（步长 2）
    - 男款：
        * 范围: XS, S, M, L, XL, XXL, 3XL, 4XL
    其它（童款/未知）暂不处理，保持原样。
    """
    if size_map is None:
        return size_map, detail

    if not size_map:
        # 没有任何尺码：只有在女款/男款才考虑补一整套
        g = gender or ""
        if "女" not in g and "男" not in g:
            return size_map, detail
    else:
        g = gender or ""
        # 有尺码也要照样补范围
        # g 取自上层 _infer_gender，通常为 "女款"/"男款"/"童款"/"未知"
    
    g = gender or ""
    g_is_female = "女" in g
    g_is_male = "男" in g

    import re

    base_sizes: list[str] = []

    if g_is_female:
        # 判断现有尺码是否是"数字系"
        has_digit = any(re.search(r"\d", s) for s in size_map.keys())

        # 只有尺码本身全部是数字（如 6, 8, 10）才算数字系；
        # 含字母的尺码（2XL, 3XL）不应触发数字模式
        has_digit = any(re.fullmatch(r"\d+", s) for s in size_map.keys())

        if has_digit:
            # 女款数字尺码：6 - 24，步长 2
            base_sizes = [str(x) for x in range(6, 26, 2)]
        else:
            # 女款字母尺码：XS - XL
            base_sizes = ["XS", "S", "M", "L", "XL"]

    elif g_is_male:
        # 男款：XS - 4XL
        base_sizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]

    else:
        # 童款 / 未知性别：不做补码
        return size_map, detail

    # 对于范围内每个尺码，若不存在则补一条"无货，库存 0"
    for sz in base_sizes:
        if sz in size_map:
            continue
        size_map[sz] = "无货"
        detail[sz] = {
            "stock_count": 0,
            "ean": "0000000000000",
        }

    return size_map, detail

def _clean_size_label(label: str) -> str:
    """
    通用垃圾清洗：
    - PRODUCT NAME IS 开头的错误内容 → ONE_SIZE
    - 年龄尺码：16YRS / 16 YRS / 16 YEARS → 16Y
    - ONE SIZE / Onesize → ONE_SIZE
    """
    if not label:
        return label

    s = str(label).strip()
    if not s:
        return s

    up = s.upper()

    # 1) 明显不是尺码，而是文案被误塞进来了
    if up.startswith("PRODUCT NAME IS"):
        return "ONE_SIZE"

    # 2) 年龄制尺码：16YRS / 16 YRS / 16 YEARS → 16Y
    m = re.match(r"^(\d+)\s*(YRS?|YEARS)$", up)
    if m:
        return f"{m.group(1)}Y"

    # 3) ONE SIZE 统一成 ONE_SIZE
    if up in ("ONE SIZE", "ONESIZE"):
        return "ONE_SIZE"

    return s


def _normalize_size_label(label: str) -> str:
    """
    清洗 M&S 服装尺码：
    - Extra Small -> XS, Medium -> M 等
    - 如果包含数字（8, 10, 12, 8-10 之类），视为数字尺码，原样保留
    - 年龄尺码 16YRS / 13YRS → 16Y / 13Y
    - "PRODUCT NAME IS ..." 等异常文本 → ONE_SIZE
    """
    if label is None:
        return label

    # 先做通用清洗（YRS / ONE SIZE / PRODUCT NAME IS...）
    label = _clean_size_label(label)
    if not label:
        return label

    # 只要含有数字，统一当作数字/年龄尺码，不再做 XS/S/M/L 映射
    # 例如：8、10、12、8-10、16Y 等都直接返回
    if re.search(r"\d", label):
        return label

    lower = label.lower().strip()

    # 去掉前缀 "size "
    if lower.startswith("size "):
        lower = lower[5:].strip()

    mapping = {
        # 这里根据你原来的映射补全即可
        "extra small": "XS",
        "xs": "XS",
        "small": "S",
        "s": "S",
        "medium": "M",
        "m": "M",
        "large": "L",
        "l": "L",
        "extra large": "XL",
        "xl": "XL",
        "extra extra large": "XXL",
        "xxl": "XXL",
        "extra extra extra large": "3xl",
        "3xl": "3XL",
    }

    if lower in mapping:
        return mapping[lower]

    # 再统一一下 ONE SIZE（防止有 "one size" 漏网）
    if lower in ("one size", "onesize"):
        return "ONE_SIZE"

    # 其它情况，保持原样
    return label



def _clean(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _load_json_safe(text: str):
    if not text:
        return None
    text = text.replace("undefined", "null")
    try:
        return json.loads(text)
    except Exception:
        return None

def _get_color_from_url(url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    if "color" in qs and qs["color"]:
        return qs["color"][0]
    return ""

def _normalize_color_code(color: str) -> str:
    """
    color: CHARTREUSE, FadedBlue, Navy/White 等
    规范化为大写、无空格无符号：
    CHARTREUSE → CHARTREUSE
    Faded Blue → FADEDBLUE
    Navy/White → NAVYWHITE
    """
    if not color:
        return ""
    s = re.sub(r"[^A-Za-z0-9]+", "", color)
    return s.upper()



def _extract_jsonld_breadcrumbs(soup: BeautifulSoup) -> list[str]:
    """
    从页面 JSON-LD BreadcrumbList 提取面包屑文本和路径。
    例: ["Home", "/", "Men", "/c/men", "Men's Knitwear", "/l/men/mens-knitwear"]
    用于 _infer_gender 判断性别。
    """
    results: list[str] = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = _load_json_safe(tag.string)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("@type") != "BreadcrumbList":
            continue
        for item in (data.get("itemListElement") or []):
            inner = item.get("item") or {}
            name = inner.get("name") or ""
            path = inner.get("@id") or ""
            if name:
                results.append(name)
            if path:
                results.append(path)
    return results


def _extract_product_sheet(soup: BeautifulSoup):
    """
    从 <script id="__NEXT_DATA__"> 中取商品核心信息

    优先使用旧结构的 pageProps.productSheet；
    若不存在，则适配新结构的 pageProps.productDetails，
    构造一个"仿 productSheet"的 dict，让后续解析逻辑复用。
    """
    tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
    if not tag:
        return None

    data = _load_json_safe(tag.string)
    if not isinstance(data, dict):
        return None

    page_props = (data.get("props") or {}).get("pageProps") or {}

    # 1️⃣ 旧结构：直接存在 productSheet
    sheet = page_props.get("productSheet")
    if sheet:
        return sheet

    # 2️⃣ 新结构：只有 productDetails，需要自己适配
    pd = page_props.get("productDetails")
    if not isinstance(pd, dict):
        return None

    attrs = pd.get("attributes") or {}
    variants = pd.get("variants") or []
    first_variant = variants[0] if variants else {}
    skus = first_variant.get("skus") or []

    # ✅ 商品名称：优先用页面展示的 masterProductDescription
    marketing_name = attrs.get("masterProductDescription")
    sheet_name = marketing_name or pd.get("name") or ""

    # ---------- prices: 构造成旧的 prices.current / prices.previous ----------
    prices = {}
    if skus:
        sku_price = (skus[0].get("price") or {})
        cur = sku_price.get("currentPrice")
        prev = sku_price.get("previousPrice")
        prices = {
            "current": cur,
            "previous": prev,
        }

    # ---------- features: 用描述 + 成分 + Inline bullets ----------
    features = []

    # 商品文案描述
    desc_html = attrs.get("masterAspirationalText") or attrs.get("furtherDescription") or ""
    if desc_html:
        features.append({"name": "Description", "value": desc_html})

    # 成分信息
    comp = attrs.get("compositionList")
    if comp:
        features.append({"name": "Composition", "value": comp})

    # Inline bullets（例如 Fit and style / Care and composition）
    for key in ("inlineReferenceBullet1", "inlineReferenceBullet2", "inlineReferenceBullet3"):
        val = attrs.get(key)
        if val:
            # M&S 这里通常是 "Fit and style#Regular fit;Button fastening" 这种形式
            features.append({"name": key, "value": val})

    # ---------- sizes: 适配成原先 sheet['sizes'] 的结构 ----------
    sizes = []
    for sku in skus:
        size_obj = sku.get("size") or {}
        size_label = (
            size_obj.get("primarySize")
            or size_obj.get("secondarySize")
            or ""
        )
        if not size_label:
            continue

        inv = sku.get("inventory") or {}
        qty = inv.get("quantity") or 0

        # M&S 这里暂时没有 EAN，就用占位符，后面 _extract_sizes 会照常使用
        ean = "0000000000000"

        sizes.append({
            "value": str(size_label),
            "stock": qty,
            "ean": ean,
        })

    # ---------- color: 适配成原先 sheet['color'] 的结构 ----------
    colour_name = first_variant.get("colour")
    color = {"name": colour_name} if colour_name else None

    # ---------- department（用于性别判断）----------
    department = (
        attrs.get("department")
        or attrs.get("gender")
        or attrs.get("targetGender")
        or ""
    )

    # ---------- breadcrumbs（用于性别判断的备用信息）----------
    breadcrumbs_raw = page_props.get("breadcrumbs") or pd.get("breadcrumbs") or []
    breadcrumb_labels = [
        (b.get("label") or b.get("name") or b.get("text") or "")
        for b in breadcrumbs_raw if isinstance(b, dict)
    ]

    # ---------- 拼成"仿 productSheet"的 dict ----------
    sheet_new = {
        "name": sheet_name,
        "code": attrs.get("strokeId") or pd.get("productExternalId") or pd.get("id"),
        "description": desc_html or "",
        "features": features,
        "prices": prices,
        "sizes": sizes,
        "color": color,
        "department": department,
        "breadcrumbs": breadcrumb_labels,
    }

    return sheet_new



# ===================== 价格解析 =====================

def _parse_price(sheet: dict):
    """
    返回：Product Price（原价） 和 Adjusted Price（折后价）
    """
    prices = sheet.get("prices") or {}
    cur = prices.get("current")
    prev = prices.get("previous")

    # 转 float
    def _to_float(x):
        try:
            return float(x)
        except:
            return None

    cur_f = _to_float(cur)
    prev_f = _to_float(prev)

    # previous > current → 有折扣
    if prev_f and cur_f and prev_f > cur_f:
        return prev_f, cur_f

    # 无折扣，只有 current
    if cur_f:
        return cur_f, 0

    return "No Data", 0


# ===================== 材质与 Feature =====================

def _extract_features(sheet: dict):
    """
    返回：features_text、material
    """
    features = sheet.get("features") or []
    feat_list = []
    material = "No Data"

    for f in features:
        name = f.get("name") or ""
        val_html = f.get("value") or ""
        txt = _clean(BeautifulSoup(val_html, "html.parser").get_text(" ", strip=True))
        if txt:
            feat_list.append(txt)

        # 找材质关键词
        low = name.lower()
        if material == "No Data" and any(k in low for k in
            ["fabric", "material", "composition", "shell", "outer", "lining"]):
            material = txt

    features_text = " | ".join(feat_list) if feat_list else "No Data"

    # 若没找到材质，尝试从 features_text 抓 65% polyester 类似字段
    if material == "No Data":
        m = re.search(r"\d+%[^|]+", features_text)
        if m:
            material = m.group(0).strip()

    return features_text, material


# ===================== 尺码解析 =====================

def _extract_sizes(sheet: dict, gender: str | None = None):
    """
    返回 SizeMap, SizeDetail（dict）
    交给 common.txt_writer.format_txt 去渲染：
      Product Size:        "XS:有货;S:无货;..."
      Product Size Detail: "XS:3:EAN;S:0:EAN;..."
    """
    sizes = sheet.get("sizes") or []
    size_map: dict[str, str] = {}
    detail: dict[str, dict] = {}

    for s in sizes:
        raw_label = s.get("value") or s.get("name")
        size_label = _normalize_size_label(raw_label)
        if not size_label:
            continue

        # quantity / stock / available：字段名兼容
        qty_raw = s.get("quantity", s.get("stock"))
        try:
            qty = int(qty_raw) if qty_raw is not None else 0
        except Exception:
            qty = 0

        available = s.get("available")
        if available is None:
            available = qty > 0
        else:
            available = bool(available)

        stock_flag = "有货" if available and qty > 0 else "无货"
        stock_count = qty if stock_flag == "有货" else 0

        ean = (s.get("ean") or "").strip() or "0000000000000"

        if size_label in size_map:
            # 同一尺码多条记录：合并库存 / 状态 / EAN
            prev_flag = size_map[size_label]
            prev_detail = detail[size_label]

            prev_detail["stock_count"] += stock_count

            if prev_flag == "有货" or stock_flag == "有货":
                size_map[size_label] = "有货"

            if prev_detail.get("ean") in ("", "0000000000000") and ean not in ("", "0000000000000"):
                prev_detail["ean"] = ean
        else:
            size_map[size_label] = stock_flag
            detail[size_label] = {
                "stock_count": stock_count,
                "ean": ean,
            }

    # ⚠️ 在这里进行"补码补 0"逻辑
    size_map, detail = _apply_size_range_completion(size_map, detail, gender)

    return size_map, detail




# ===================== 颜色，性别，类目 =====================

def _extract_color(sheet: dict, url: str):
    color_data = sheet.get("color")
    if isinstance(color_data, dict):
        c = color_data.get("name")
        if c:
            return _clean(c)

    m = re.search(r"[?&]color=([^&#]+)", url, re.I)
    if m:
        return _clean(m.group(1))

    return "No Data"


def _infer_gender(name: str, sheet: dict, url: str):
    l = name.lower()
    u = url.lower()

    # 童款优先判断
    if any(k in l for k in ["girl", "boys", "kids"]) or "/kids/" in u:
        return "童款"

    # 从 JSON 里取 department 和 breadcrumbs（最可靠，不依赖 URL 结构）
    dept = str(sheet.get("department") or "").lower()
    crumbs = " ".join(str(c) for c in (sheet.get("breadcrumbs") or [])).lower()

    # 用词边界匹配 "men"，避免 "women" 误命中
    # 检查顺序：department → breadcrumbs → 商品名 → URL 路径
    for text in (dept, crumbs, l):
        if re.search(r"\bmen\b", text) and "women" not in text:
            return "男款"

    if re.search(r"/men[s]?/", u):
        return "男款"

    return "女款"




# ===================== 单页面解析 =====================

def extract_page(url: str) -> dict:
    """使用 Selenium 加载页面并解析"""
    driver = get_driver("marksandspencer", headless=True)
    driver.get(url)

    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
    except:
        time.sleep(5)

    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = _clean(title_tag.text) if title_tag else "No Data"

    # --- 解析核心 JSON ---
    sheet = _extract_product_sheet(soup)
    if not sheet:
        raise Exception("没有找到 productSheet")

    # 用 JSON-LD BreadcrumbList 补充面包屑（包含 "Men"/"Women" 等路径，比 __NEXT_DATA__ 更可靠）
    jsonld_crumbs = _extract_jsonld_breadcrumbs(soup)
    if jsonld_crumbs:
        sheet["breadcrumbs"] = (sheet.get("breadcrumbs") or []) + jsonld_crumbs

    name = _clean(sheet.get("name") or title)



    base_code = sheet.get("code") or "NoCode"

    # 从 URL 提取颜色
    url_color = _get_color_from_url(url)
    color_suffix = _normalize_color_code(url_color)

    # 如果 URL 给了颜色，就把颜色加入编码
    if color_suffix:
        code = f"{base_code}_{color_suffix}"
    else:
        # 单色商品：保持原始款式编码
        code = base_code








    desc = _clean(sheet.get("description") or "")

    # 价格
    price, discount = _parse_price(sheet)

    # 特征 / 材质
    feature, material = _extract_features(sheet)

    # 颜色
    color = _extract_color(sheet, url)

    # 性别 / 类目（必须放在尺码解析之前）
    gender = _infer_gender(name, sheet, url)
    category = normalize_style_category("", name)

    # 尺码（返回 SizeMap/SizeDetail，符合鲸芽格式）
    size_map, size_detail = _extract_sizes(sheet, gender)

    # 直接交给 txt_writer 生成鲸芽格式 Product Size / Product Size Detail
    info = {
        "Product Code": code,
        "Product Name": name,
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": price,
        "Adjusted Price": discount,
        "Product Material": material,
        "Style Category": category,
        "Feature": feature,

        # ⬇⬇⬇ 新字段，鲸芽模式必须有
        "SizeMap": size_map,
        "SizeDetail": size_detail,

        "Site Name": CANON_SITE,
        "Source URL": url,
    }
    return info



# ===================== Pipeline 主入口 =====================

def fetch_jackcet_info():
    """M&S 全品类（服装）抓取入口"""
    links_file: Path = MARKSANDSPENCER["LINKS_FILE_JACKET"]
    txt_dir: Path = MARKSANDSPENCER["TXT_DIR"]
    txt_dir.mkdir(parents=True, exist_ok=True)

    if not links_file.exists():
        print(f"❌ 未找到链接文件: {links_file}")
        return

    urls = [
        ln.strip()
        for ln in links_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    print(f"📄 共 {len(urls)} 个 M&S 商品待抓取")

    for idx, url in enumerate(urls, 1):
        print(f"\n—— [{idx}/{len(urls)}] ——")
        try:
            info = extract_page(url)

            fname = info["Product Code"].replace("/", "_")
            txt_path = txt_dir / f"{fname}.txt"

            format_txt(info, txt_path, brand="marksandspencer")

            print(f"✅ 成功写入 TXT: {txt_path.name}")

        except Exception as e:
            print(f"❌ 解析失败: {url}\n   错误: {e}")


if __name__ == "__main__":
    fetch_jackcet_info()
