from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 4  # 建议 3~5

def pick_public_prices(product_sheet: dict):
    prices = product_sheet.get("prices") or {}
    cur = _safe_float(prices.get("current"))
    prev = _safe_float(prices.get("previous"))
    if cur > 0 and prev > 0 and cur < prev:
        return prev, cur, "public"
    if cur > 0:
        return cur, cur, "no_discount"
    return 0.0, 0.0, "no_price"

def worker_public(product_url: str):
    driver = None
    try:
        driver = get_driver(name="camper_public_mt", headless=True)
        # 这里复用你原来的解析，但把价格函数替换成 public 版本：
        return process_product_url_with_driver_public(driver, product_url)
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

def process_product_url_with_driver_public(driver, product_url: str):
    print(f"\n🔍 正在访问: {product_url}")
    driver.get(product_url)
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.0)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    title_tag = soup.find("title")
    product_title = (
        re.sub(r"\s*[-–—].*", "", title_tag.text.strip())
        if title_tag and title_tag.text
        else "Unknown Title"
    )

    script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
    if not script_tag or not script_tag.string:
        raise RuntimeError("未找到 __NEXT_DATA__")

    json_data = json.loads(script_tag.string)
    product_sheet = json_data.get("props", {}).get("pageProps", {}).get("productSheet")
    if not product_sheet:
        raise RuntimeError("未找到 productSheet")

    data = product_sheet
    product_code = data.get("code", "Unknown_Code")
    description = data.get("description", "")

    # ✅ public price
    original_price, discount_price, price_src = pick_public_prices(data)

    color_data = data.get("color", "")
    color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

    features_raw = data.get("features") or []
    feature_texts = []
    for f in features_raw:
        value_html = (f.get("value") or "")
        clean_text = BeautifulSoup(value_html, "html.parser").get_text(strip=True)
        if clean_text:
            feature_texts.append(clean_text)
    feature_str = " | ".join(feature_texts) if feature_texts else "No Data"

    upper_material = "No Data"
    for feature in features_raw:
        name = (feature.get("name") or "").lower()
        if "upper" in name:
            raw_html = feature.get("value") or ""
            upper_material = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
            break

    size_map = {}
    size_detail = {}
    for s in data.get("sizes", []):
        value = (s.get("value", "") or "").strip()
        available = bool(s.get("available", False))
        quantity = s.get("quantity", 0)
        ean = s.get("ean", "")
        size_map[value] = "有货" if available else "无货"
        size_detail[value] = {"stock_count": quantity, "ean": ean}

    gender = infer_gender_from_url(product_url)

    standard_sizes = SIZE_RANGE_CONFIG.get("camper", {}).get(gender, [])
    if standard_sizes:
        for x in [x for x in standard_sizes if x not in size_detail]:
            size_map[x] = "无货"
            size_detail[x] = {"stock_count": 0, "ean": ""}

    style_category = infer_style_category(description)

    info = {
        "Product Code": product_code,
        "Product Name": product_title,
        "Product Description": description,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": str(original_price),
        "Adjusted Price": str(discount_price),
        "Product Material": upper_material,
        "Style Category": style_category,
        "Feature": feature_str,
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Source URL": product_url,
        "Price Source": price_src,
    }

    out_path = Path(SAVE_PATH) / f"{product_code}.txt"
    format_txt(info, out_path, brand="camper")
    print(f"✅ 完成 TXT: {out_path.name} (src={price_src}, P={original_price}, D={discount_price})")
    return product_code, price_src

def camper_fetch_product_info_public_mt(product_urls_file: Optional[str] = None):
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    failed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(worker_public, url): url for url in urls}
        for fu in as_completed(futures):
            url = futures[fu]
            try:
                fu.result()
            except Exception as e:
                print(f"❌ 失败: {url} - {e}")
                failed.append(url)

    if failed:
        fail_path = Path(SAVE_PATH).resolve().parent / "failed_urls_public_mt.txt"
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        print(f"⚠️ 失败链接已输出: {fail_path}")

if __name__ == "__main__":
    camper_fetch_product_info_public_mt()
