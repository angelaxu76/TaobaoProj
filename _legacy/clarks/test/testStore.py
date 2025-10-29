from config import CLARKS
from common_taobao.publication.prepare_utils_extended import get_publishable_product_codes

store = "五小剑"  # 或 "五小剑"
codes = get_publishable_product_codes(CLARKS, store)
print(f"🟢 店铺 [{store}] 可发布商品数: {len(codes)}")
print("部分编码预览:", codes[:10])
