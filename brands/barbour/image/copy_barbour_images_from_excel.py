import os
import shutil
from typing import Tuple, List

import pandas as pd


def copy_barbour_images_from_excel(
    excel_path: str,
    images_root: str,
    target_root: str,
) -> Tuple[int, int, List[str]]:
    """
    从 Excel 读取商品编码列表，把 images_root 下对应编码文件夹内的图片复制到 target_root。

    参数：
      excel_path:  Excel 文件路径
      images_root: 所有图片集合根目录（每个商品一个编码文件夹）
      target_root: 目标根目录（会自动创建；每个商品也会创建一个编码文件夹）

    返回：
      (成功复制的商品数, 缺失图片文件夹的商品数, 缺失的编码列表)
    """
    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"Excel 不存在: {excel_path}")
    if not os.path.isdir(images_root):
        raise NotADirectoryError(f"images_root 不是目录或不存在: {images_root}")

    os.makedirs(target_root, exist_ok=True)

    df = pd.read_excel(excel_path, dtype=str)
    if "商品编码" not in df.columns:
        raise ValueError(f"Excel 中找不到列：商品编码。当前列：{list(df.columns)}")

    # 去重 + 清洗
    codes = (
        df["商品编码"]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )

    copied_products = 0
    missing_products = 0
    missing_codes: List[str] = []

    for code in codes:
        src_dir = os.path.join(images_root, code)
        if not os.path.isdir(src_dir):
            missing_products += 1
            missing_codes.append(code)
            continue

        dst_dir = os.path.join(target_root, code)
        os.makedirs(dst_dir, exist_ok=True)

        # 复制该编码文件夹下的所有文件（可按需改成只复制 jpg/png/webp）
        any_file = False
        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            if not os.path.isfile(src_path):
                continue
            any_file = True
            dst_path = os.path.join(dst_dir, name)
            shutil.copy2(src_path, dst_path)  # 同名覆盖

        # 统计：只有确实复制了文件才算“成功复制的商品”
        if any_file:
            copied_products += 1
        else:
            # 文件夹存在但没文件，也算缺失（按你业务更安全）
            missing_products += 1
            missing_codes.append(code)

    return copied_products, missing_products, missing_codes


import os
from typing import List


def rebuild_image_indexes(
    product_dir: str,
    product_code: str,
):
    """
    按规则重命名单个商品文件夹内的图片：
    - 确保存在 product_code_0.jpg（第一张）
    - 确保存在 product_code_9.jpg（最后一张）
    - 其他图片按 1,2,3... 命名，跳过 9
    """

    exts = (".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG", ".WEBP")

    files = [
        f for f in os.listdir(product_dir)
        if f.lower().endswith(exts)
    ]

    if not files:
        return  # 空目录直接跳过

    # 排序，保证顺序稳定（按文件名）
    files.sort()

    def has_index(idx: int) -> bool:
        return any(
            f.lower().endswith(f"_{idx}.jpg")
            for f in files
        )

    # ---- 第一步：准备 0.jpg 和 9.jpg ----
    rename_map = {}

    remaining = files.copy()

    # 0.jpg
    if not has_index(0):
        first = remaining.pop(0)
        rename_map[first] = f"{product_code}_0.jpg"

    # 9.jpg
    if not has_index(9) and remaining:
        last = remaining.pop(-1)
        rename_map[last] = f"{product_code}_9.jpg"

    # ---- 第二步：处理中间图片 ----
    index = 1
    for f in remaining:
        if index == 9:
            index = 10
        rename_map[f] = f"{product_code}_{index}.jpg"
        index += 1

    # ---- 第三步：实际执行重命名（先临时名，避免覆盖）----
    temp_map = {}
    for src, dst in rename_map.items():
        src_path = os.path.join(product_dir, src)
        tmp_path = os.path.join(product_dir, f"__tmp__{src}")
        os.rename(src_path, tmp_path)
        temp_map[tmp_path] = os.path.join(product_dir, dst)

    for tmp_path, final_path in temp_map.items():
        os.rename(tmp_path, final_path)


if __name__ == "__main__":
    # ===== 示例用法（按你的实际路径改）=====
    excel_path = r"D:\TB\Products\barbour\publication\barbour_publication.xlsx"
    images_root = r"D:\TB\Products\barbour\images"
    target_root = r"D:\TB\Products\barbour\publication\images_selected"

    ok, miss, miss_list = copy_barbour_images_from_excel(excel_path, images_root, target_root)

    print(f"完成：成功复制商品数 = {ok}")
    print(f"缺失：缺失商品数 = {miss}")
    if miss_list:
        print("缺失编码示例（最多20个）：", miss_list[:20])
