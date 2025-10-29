from common_taobao.publication.prepare_utils_extended import get_publishable_product_codes
from config import BRAND_CONFIG

# 设置品牌和店铺
brand = "clarks"
store = "五小剑"

# 获取配置
config = BRAND_CONFIG[brand]

# 调用函数
codes = get_publishable_product_codes(config, store)

# 输出结果
print(f"✅ 共找到 {len(codes)} 个待发布商品编码：")
for code in codes:
    print(" -", code)
