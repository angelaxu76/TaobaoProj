import os
import shutil
import pandas as pd
from typing import Tuple, List


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _is_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTS)


def copy_barbour_images_from_excel(
    excel_path: str,
    images_root: str,
    target_root: str,
    verbose: bool = True,
    missing_txt_path: str | None = None,
) -> Tuple[int, int, List[str]]:
    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"Excel 不存在: {excel_path}")
    if not os.path.isdir(images_root):
        raise NotADirectoryError(f"images_root 不是目录或不存在: {images_root}")

    os.makedirs(target_root, exist_ok=True)

    df = pd.read_excel(excel_path, dtype=str)
    if "商品编码" not in df.columns:
        raise ValueError(f"Excel 中找不到列：商品编码。当前列：{list(df.columns)}")

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

        any_file = False
        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            if not os.path.isfile(src_path):
                continue
            any_file = True
            shutil.copy2(src_path, os.path.join(dst_dir, name))

        if any_file:
            copied_products += 1
        else:
            missing_products += 1
            missing_codes.append(code)

    if verbose:
        print(f"[COPY] ok={copied_products}, missing={missing_products}")
        if missing_codes:
            print("[COPY] Missing codes:")
            for c in missing_codes:
                print("  -", c)

    if missing_txt_path and missing_codes:
        os.makedirs(os.path.dirname(missing_txt_path), exist_ok=True)
        with open(missing_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(missing_codes))
        if verbose:
            print(f"[COPY] Missing codes saved to: {missing_txt_path}")

    return copied_products, missing_products, missing_codes



from typing import List, Tuple

def rebuild_image_indexes(product_dir: str, product_code: str, verbose: bool = True) -> List[Tuple[str, str]]:
    """
    返回：[(old_name, new_name), ...]
    """
    files = [f for f in os.listdir(product_dir) if os.path.isfile(os.path.join(product_dir, f)) and _is_image(f)]
    if not files:
        return []

    files.sort()

    def is_index_file(f: str, idx: int) -> bool:
        base = os.path.splitext(f)[0].lower()
        return base == f"{product_code.lower()}_{idx}"

    has_0 = any(is_index_file(f, 0) for f in files)
    has_9 = any(is_index_file(f, 9) for f in files)

    fixed = set([f for f in files if is_index_file(f, 0) or is_index_file(f, 9)])
    remaining = [f for f in files if f not in fixed]

    rename_map = {}

    if (not has_0) and remaining:
        first = remaining.pop(0)
        rename_map[first] = f"{product_code}_0.jpg"

    if (not has_9) and remaining:
        last = remaining.pop(-1)
        rename_map[last] = f"{product_code}_9.jpg"

    idx = 1
    for f in remaining:
        if idx == 9:
            idx = 10
        rename_map[f] = f"{product_code}_{idx}.jpg"
        idx += 1

    if not rename_map:
        if verbose:
            print(f"[RENAME] {product_code}: nothing to rename")
        return []

    # 两段式重命名避免覆盖
    actions: List[Tuple[str, str]] = []

    temp_paths = {}
    for src, dst in rename_map.items():
        src_path = os.path.join(product_dir, src)
        tmp_path = os.path.join(product_dir, f"__tmp__{src}")
        os.rename(src_path, tmp_path)
        temp_paths[tmp_path] = os.path.join(product_dir, dst)

    for tmp_path, final_path in temp_paths.items():
        old_name = os.path.basename(tmp_path).replace("__tmp__", "", 1)
        new_name = os.path.basename(final_path)
        os.rename(tmp_path, final_path)
        actions.append((old_name, new_name))

    if verbose:
        print(f"[RENAME] {product_code}: {len(actions)} file(s)")
        for o, n in actions:
            print(f"  {o}  ->  {n}")

    return actions



def rebuild_all_products_images(target_root: str, verbose: bool = True):
    total_products = 0
    changed_products = 0
    total_files = 0

    for code in os.listdir(target_root):
        product_dir = os.path.join(target_root, code)
        if not os.path.isdir(product_dir):
            continue

        total_products += 1
        actions = rebuild_image_indexes(product_dir, code, verbose=verbose)
        if actions:
            changed_products += 1
            total_files += len(actions)

    if verbose:
        print(f"[RENAME] products scanned={total_products}, changed={changed_products}, files renamed={total_files}")

def collect_all_images_to_flat_dir(
    target_root: str,
    flat_target_dir: str,
    verbose: bool = True,
):
    """
    将 target_root 下所有商品编码目录中的图片
    集中复制到 flat_target_dir 中（扁平结构）
    """

    if not os.path.isdir(target_root):
        raise NotADirectoryError(f"target_root 不存在或不是目录: {target_root}")

    os.makedirs(flat_target_dir, exist_ok=True)

    total_products = 0
    total_images = 0

    for code in os.listdir(target_root):
        product_dir = os.path.join(target_root, code)
        if not os.path.isdir(product_dir):
            continue

        total_products += 1

        for name in os.listdir(product_dir):
            if not _is_image(name):
                continue

            src_path = os.path.join(product_dir, name)
            if not os.path.isfile(src_path):
                continue

            dst_path = os.path.join(flat_target_dir, name)
            shutil.copy2(src_path, dst_path)
            total_images += 1

            if verbose:
                print(f"[COLLECT] {code}/{name}  ->  {dst_path}")

    if verbose:
        print(f"[COLLECT] products={total_products}, images={total_images}")


def watermark_index_0_9_inplace(
    flat_images_dir: str,
    watermark_text: str = "英国哈梅尔百货",
    verbose: bool = True,
):
    """
    只对 flat_images_dir 中 *_0.* 和 *_9.* 的图片加水印
    直接覆盖原图（in-place）
    """

    from PIL import Image


    import helper.image.add_text_watermark as wm
    from helper.image.add_text_watermark import (
        add_diagonal_text_watermark,
        add_local_logo,
    )

    if not os.path.isdir(flat_images_dir):
        raise NotADirectoryError(f"目录不存在: {flat_images_dir}")

    # 覆盖你水印脚本里的全局文案
    wm.DIAGONAL_TEXT = watermark_text
    wm.LOCAL_LOGO_TEXT = watermark_text

    processed = 0
    skipped = 0
    failed = 0

    for fname in os.listdir(flat_images_dir):
        path = os.path.join(flat_images_dir, fname)

        if not os.path.isfile(path):
            continue
        if not _is_image(fname):
            continue

        base = os.path.splitext(fname)[0].lower()

        # ✅ 只处理 _0 / _9
        if not (base.endswith("_0") or base.endswith("_9")):
            skipped += 1
            continue

        try:
            img = Image.open(path).convert("RGB")
            img = add_diagonal_text_watermark(img)
            img = add_local_logo(img)

            img.save(path, quality=95)  # 直接覆盖
            processed += 1

            if verbose:
                print(f"[WATERMARK] 覆盖成功: {fname}")

        except Exception as e:
            failed += 1
            if verbose:
                print(f"[WATERMARK] ❌ 失败: {fname} -> {e}")

    if verbose:
        print(
            f"[WATERMARK] 完成 | 处理={processed}, 跳过={skipped}, 失败={failed}"
        )


if __name__ == "__main__":
    excel_path = r"D:\TB\Products\barbour\publication\barbour_publication.xlsx"
    images_root = r"D:\TB\Products\barbour\images"

    # ✅ 关键：改成你实际在用的目录
    target_root = r"D:\TB\Products\barbour\repulibcation\images_selected"

    ok, miss, miss_list = copy_barbour_images_from_excel(excel_path, images_root, target_root)
    rebuild_all_products_images(target_root)

    print(f"完成：成功复制商品数 = {ok}")
    print(f"缺失：缺失商品数 = {miss}")
    if miss_list:
        print("缺失编码示例（最多20个）：", miss_list[:20])
