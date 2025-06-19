from common_taobao.prepare_utils_extended import generate_product_excels
from config import BRAND_CONFIG

# ✅ 指定品牌与店铺
brand = "ecco"
store = "英国伦敦代购"  # 可根据需要替换成实际店铺名

# 获取配置并调用统一逻辑
config = BRAND_CONFIG[brand]
generate_product_excels(config, store)