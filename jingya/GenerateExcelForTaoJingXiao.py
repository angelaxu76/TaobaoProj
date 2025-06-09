import os
import pandas as pd
import re
import requests
import deepl  # pip install deepl

# 参数集中管理
output_file_path = r'D:\TB\Products\camper\publication\code.txt'  # output.txt路径
texts_folder = r'D:\TB\Products\camper\Resource\CAMPER_TEXTS'  # 各编码的txt文件夹
save_excel_path = r'D:\TB\Products\camper\publication\result.xlsx'  # 保存生成的excel路径

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

# 默认英镑汇率
default_exchange_rate = 9.1  # 可手动修改

# DeepL API KEY（需要你自己注册填进去）
auth_key = "fbeb00ce-2b94-42c8-9126-65daaaf0e7dd:fx"  # <<< 请把这里的 YOUR_DEEPL_API_KEY 换成你自己的DeepL API Key
translator = deepl.Translator(auth_key)

# 获取实时英镑兑人民币汇率
def get_exchange_rate():
    try:
        response = requests.get('https://api.exchangerate.host/latest?base=GBP&symbols=CNY', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data['rates']['CNY']
    except Exception as e:
        print(f"获取实时汇率失败，使用默认汇率。错误信息: {e}")
    return default_exchange_rate

# 翻译英文为中文
def translate_text(text):
    try:
        result = translator.translate_text(text, source_lang="EN", target_lang="ZH")
        return result.text
    except Exception as e:
        print(f"翻译失败，保留英文标题: {text}")
        return text

# 获取当前汇率
exchange_rate = get_exchange_rate()
print(f"当前英镑兑人民币汇率: {exchange_rate}")

# 读取output.txt编码列表
with open(output_file_path, 'r', encoding='utf-8') as f:
    product_codes = [line.strip() for line in f if line.strip()]

# 定义一个列表收集所有行数据
rows = []

# 逐个处理
for code in product_codes:
    txt_file_path = os.path.join(texts_folder, f"{code}.txt")
    if not os.path.exists(txt_file_path):
        print(f"警告: 找不到文件 {txt_file_path}")
        continue

    with open(txt_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取字段函数
    def extract_field(name, content):
        start = content.find(name)
        if start == -1:
            return ""
        start = content.find(':', start) + 1
        end = content.find('\n', start)
        return content[start:end].strip()

    product_title = extract_field('Product Title', content)
    product_price_raw = extract_field('Product price', content).replace('GBP', '').strip()

    # 标题处理
    product_title = product_title.replace('United Kingdom', '').strip()
    product_title_cn = translate_text(product_title)

    # 价格计算
    try:
        product_price_raw = float(product_price_raw)
        rmb_price = (product_price_raw * 0.75 + 6) * exchange_rate * 1.2
        rmb_price = round(rmb_price, 2)
    except:
        rmb_price = ""

    # 材质判断
    lining_info = content.lower()
    upper_info = content.lower()

    if 'recycled polyester' in lining_info:
        lining_material = "织物"
    elif 'leather' in lining_info:
        lining_material = "头层牛皮"
    else:
        lining_material = ""

    if 'recycled polyester' in upper_info:
        upper_material = "织物"
    elif 'leather' in upper_info:
        upper_material = "牛皮革"
    else:
        upper_material = ""

    # HSCODE判断
    if 'upper' in content.lower() and 'leather' in upper_info:
        hscode = "6403990090"
    else:
        hscode = "6405200090"

    # 后跟高（Height提取）
    height_match = re.search(r'Height[:：]?\s*(\d+\.?\d*)', content, re.IGNORECASE)
    if height_match:
        height_value = float(height_match.group(1))
        if height_value > 5:
            heel_height = "高跟(5-8cm)"
        elif 3 <= height_value <= 5:
            heel_height = "中跟(3-5cm)"
        else:
            heel_height = "低跟(1-3cm)"
    else:
        heel_height = ""

    # 收集行数据
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

# 写入Excel
df = pd.DataFrame(rows)
df.to_excel(save_excel_path, index=False)

print(f"处理完成，总共写入 {len(rows)} 条数据，Excel已保存到: {save_excel_path}")
