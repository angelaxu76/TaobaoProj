def extract_product_codes_and_unappointProd_from_excel(txt_path, texts_folder, excel_path, exchange_rate=None):
    import os
    import re
    import requests
    import deepl
    import pandas as pd
    import time

    auth_key = "fbeb00ce-2b94-42c8-9126-65daaaf0e7dd:fx"
    translator = deepl.Translator(auth_key)

    def get_exchange_rate():
        try:
            r = requests.get('https://api.exchangerate.host/latest?base=GBP&symbols=CNY', timeout=5)
            if r.status_code == 200:
                data = r.json()
                if 'rates' in data and 'CNY' in data['rates']:
                    return data['rates']['CNY']
        except Exception as e:
            print(f"获取实时汇率失败，使用默认汇率。错误信息: {e}")
        return 9.1

    def translate_text_safe(text, retry=3, delay=5, base_delay=0.3):
        for attempt in range(retry):
            try:
                result = translator.translate_text(text, source_lang="EN", target_lang="ZH")
                time.sleep(base_delay)  # 添加延迟，避免触发限流
                return result.text
            except deepl.exceptions.TooManyRequestsException:
                print(f"🔁 第 {attempt + 1}/{retry} 次重试：DeepL 服务器限流，等待 {delay} 秒…")
                time.sleep(delay)
            except Exception as e:
                print(f"⚠️ 翻译失败：{e}")
                return text
        return text

    if exchange_rate is None:
        exchange_rate = get_exchange_rate()
    print(f"当前英镑兑人民币汇率: {exchange_rate}")

    # 固定字段
    上市季节 = "2025春季"
    季节 = "春秋"
    款式 = "休闲"
    闭合方式 = ""
    跟底款式 = "平底"
    开口深度 = "浅口"
    鞋头款式 = "圆头"
    地区国家 = "英国"
    发货时间 = "7"
    运费模版 = "parcelforce"
    第一计量单位 = "1"
    第二计量单位 = "1"
    销售单位 = "双"
    品名 = "鞋"
    海关款式 = "休闲鞋"
    外底材料 = "EVA"
    内底长度 = "27"
    品牌 = "camper"

    # 读取商品编码
    with open(txt_path, 'r', encoding='utf-8') as f:
        product_codes = [line.strip() for line in f if line.strip()]

    rows = []

    for code in product_codes:
        txt_file_path = os.path.join(texts_folder, f"{code}.txt")
        if not os.path.exists(txt_file_path):
            print(f"⚠️ 找不到文件: {txt_file_path}")
            continue

        with open(txt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        def extract_field(name, content):
            start = content.find(name)
            if start == -1:
                return ""
            start = content.find(':', start) + 1
            end = content.find('\n', start)
            return content[start:end].strip()

        product_title = extract_field('Product Title', content)
        product_price_raw = extract_field('Product price', content).replace('GBP', '').strip()

        product_title = product_title.replace('United Kingdom', '').strip()
        product_title_cn = translate_text_safe(product_title)

        try:
            product_price_raw = float(product_price_raw)
            rmb_price = (product_price_raw * 0.75 + 6) * exchange_rate * 1.2
            rmb_price = round(rmb_price, 2)
        except:
            rmb_price = ""

        lower_content = content.lower()
        lining_material = "织物" if 'recycled polyester' in lower_content else ("头层牛皮" if 'leather' in lower_content else "")
        upper_material = "织物" if 'recycled polyester' in lower_content else ("牛皮革" if 'leather' in lower_content else "")

        hscode = "6403990090" if 'upper' in lower_content and 'leather' in lower_content else "6405200090"

        height_match = re.search(r'Height[:：]?\s*(\d+\.?\d*)', content, re.IGNORECASE)
        if height_match:
            height_value = float(height_match.group(1))
            heel_height = (
                "高跟(5-8cm)" if height_value > 5 else
                "中跟(3-5cm)" if 3 <= height_value <= 5 else
                "低跟(1-3cm)"
            )
        else:
            heel_height = ""

        row = {
            "标题": product_title_cn,
            "商品编码": code,
            "价格": rmb_price,
            "内里材质": lining_material,
            "帮面材质": upper_material,
            "上市季节": 上市季节,
            "季节": 季节,
            "款式": 款式,
            "闭合方式": 闭合方式,
            "跟底款式": 跟底款式,
            "开口深度": 开口深度,
            "后跟高": heel_height,
            "鞋头款式": 鞋头款式,
            "地区国家": 地区国家,
            "发货时间": 发货时间,
            "运费模版": 运费模版,
            "HSCODE": hscode,
            "第一计量单位": 第一计量单位,
            "第二计量单位": 第二计量单位,
            "销售单位": 销售单位,
            "品名": 品名,
            "海关款式": 海关款式,
            "外底材料": 外底材料,
            "内底长度": 内底长度,
            "品牌": 品牌
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel(excel_path, index=False)
    print(f"✅ 已保存到 Excel 文件: {excel_path}")
