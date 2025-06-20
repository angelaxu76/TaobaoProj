import os
from config import CLARKS, ECCO, GEOX
from common_taobao.txt_parser import parse_txt_to_record
from common_taobao.prepare_utils_extended import generate_product_excels

BRAND_MAP = {
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def generate_product_excels_main(brand_name: str, store_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
    generate_product_excels(config, store_name)