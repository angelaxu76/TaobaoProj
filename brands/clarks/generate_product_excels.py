from common_taobao.prepare_utils_extended import generate_product_excels
from config import BRAND_CONFIG

# ✅ 直接指定品牌和店铺名称
brand = "clarks"
store = "五小剑"

# 获取配置并调用
config = BRAND_CONFIG[brand]
generate_product_excels(config, store)
