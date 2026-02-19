import os
import shutil
import pandas as pd
from typing import Tuple, List


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _is_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTS)


def _read_codes_from_excel(excel_path: str) -> List[str]:
    """从 Excel 中读取去重后的商品编码列表。"""
    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"Excel 不存在: {excel_path}")

    df = pd.read_excel(excel_path, dtype=str)
    if "商品编码" not in df.columns:
        raise ValueError(f"Excel 中找不到列：商品编码。当前列：{list(df.columns)}")

    return (
        df["商品编码"]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )


def _copy_product_folder(src_dir: str, dst_dir: str) -> bool:
    """将 src_dir 中的文件复制到 dst_dir，返回是否有文件被复制。"""
    os.makedirs(dst_dir, exist_ok=True)
    any_file = False
    for name in os.listdir(src_dir):
        src_path = os.path.join(src_dir, name)
        if not os.path.isfile(src_path):
            continue
        any_file = True
        shutil.copy2(src_path, os.path.join(dst_dir, name))
    return any_file


def prepare_images_for_publication(
    excel_path: str,
    downloaded_dir: str,
    processed_dir: str,
    publish_ready_dir: str,
    publish_need_process_dir: str,
    missing_txt_path: str,
    verbose: bool = True,
) -> Tuple[List[str], List[str], List[str]]:
    """
    为发布商品准备图片，按优先级分三步处理 Excel 中的商品编码：

    1. 已处理图片优先：如果 processed_dir/<code> 存在，移动到 publish_ready_dir/<code>
    2. 下载图片其次：如果 downloaded_dir/<code> 存在，复制到 publish_need_process_dir/<code>
    3. 都没有：记录到 missing_txt_path

    参数:
        excel_path:              Excel 文件路径（含"商品编码"列）
        downloaded_dir:          从官网下载的原始图片目录
        processed_dir:           已经处理好的图片目录
        publish_ready_dir:       输出 - 已处理好可直接发布的图片目录
        publish_need_process_dir:输出 - 已下载但还需处理的图片目录
        missing_txt_path:        输出 - 没有图片的商品编码 TXT 文件

    返回:
        (ready_codes, need_process_codes, missing_codes)
    """
    for d in [downloaded_dir, processed_dir]:
        if not os.path.isdir(d):
            raise NotADirectoryError(f"目录不存在: {d}")

    codes = _read_codes_from_excel(excel_path)

    ready_codes: List[str] = []
    need_process_codes: List[str] = []
    missing_codes: List[str] = []

    for code in codes:
        processed_src = os.path.join(processed_dir, code)
        if os.path.isdir(processed_src) and _copy_product_folder(
            processed_src, os.path.join(publish_ready_dir, code)
        ):
            ready_codes.append(code)
            if verbose:
                print(f"[READY]   {code} <- processed")
            continue

        downloaded_src = os.path.join(downloaded_dir, code)
        if os.path.isdir(downloaded_src) and _copy_product_folder(
            downloaded_src, os.path.join(publish_need_process_dir, code)
        ):
            need_process_codes.append(code)
            if verbose:
                print(f"[NEED_EDIT] {code} <- downloaded")
            continue

        missing_codes.append(code)
        if verbose:
            print(f"[MISSING] {code}")

    # 写入缺失编码
    if missing_codes:
        os.makedirs(os.path.dirname(missing_txt_path) or ".", exist_ok=True)
        with open(missing_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(missing_codes))

    if verbose:
        print(f"\n[SUMMARY] 总编码数={len(codes)}")
        print(f"  可直接发布={len(ready_codes)}")
        print(f"  需要处理={len(need_process_codes)}")
        print(f"  缺少图片={len(missing_codes)}")
        if missing_codes:
            print(f"  缺失编码已保存到: {missing_txt_path}")

    return ready_codes, need_process_codes, missing_codes



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

    downloaded_dir = r"D:\TB\Products\barbour\images_download"
    processed_dir = r"D:\TB\Products\barbour\images"
    publish_ready_dir = r"D:\TB\Products\barbour\repulibcation\images_selected"
    publish_need_process_dir = r"D:\TB\Products\barbour\repulibcation\need_edit"
    missing_txt_path = r"D:\TB\Products\barbour\repulibcation\missing_codes.txt"

    ready, need_edit, missing = prepare_images_for_publication(
        excel_path=excel_path,
        downloaded_dir=downloaded_dir,
        processed_dir=processed_dir,
        publish_ready_dir=publish_ready_dir,
        publish_need_process_dir=publish_need_process_dir,
        missing_txt_path=missing_txt_path,
    )

    rebuild_all_products_images(publish_ready_dir)
