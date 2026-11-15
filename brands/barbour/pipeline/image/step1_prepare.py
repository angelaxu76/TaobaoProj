# -*- coding: utf-8 -*-
"""
Barbour 图片流水线 step1：下载 → 防指纹 → 入长期库 → 选图 → 人物/细节分类。

前置：repulibcation/codes.xlsx 已放好本批次商品编码。
参数：image_session.py 的 step1 区块。
运行：python brands/barbour/pipeline/image/step1_prepare.py
结束后：人工剔除 classify/person 里不适合换脸的图，然后跑 step2。
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root

from cfg.brands.barbour import BARBOUR
from brands.barbour.pipeline.image import image_session as S
from brands.barbour.pipeline.image._common import (
    banner, count_codes, list_images, manual_checkpoint, read_codes,
)


def _reset_dir(path) -> None:
    p = Path(path)
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def download() -> None:
    from brands.barbour.supplier.barbour_download_images_only import download_barbour_images_multi
    from common.image.group_images_by_code import group_and_rename_images
    from helper.image.image_antifingerprint import batch_process_images

    raw_dir, processed_dir = BARBOUR["IMAGE_DOWNLOAD_RAW"], BARBOUR["IMAGE_DOWNLOAD_PROCESSED"]

    banner("1/3 下载官网图片 → 防指纹 → 按编码入长期库")
    _reset_dir(raw_dir)        # 两个中转目录只放本次散图，每次清空
    _reset_dir(processed_dir)
    download_barbour_images_multi(max_workers=6, skip_existing=not S.FORCE_REDOWNLOAD)
    batch_process_images(IMAGE_IN=raw_dir, IMAGE_OUT=processed_dir)
    group_and_rename_images(processed_dir, code_len=11, overwrite=True, dest_dir=BARBOUR["IMAGE_DOWNLOAD"])


def select() -> None:
    from common.image.copy_images_by_excel import prepare_images_for_publication

    banner("2/3 按 codes.xlsx 从长期库选图 → images_selected")
    prepare_images_for_publication(
        excel_path=S.CODES_EXCEL,
        downloaded_dir=BARBOUR["IMAGE_DOWNLOAD"],
        processed_dir=BARBOUR["IMAGE_DOWNLOAD"],
        publish_ready_dir=S.IMAGE_SELECTED,
        publish_need_process_dir=S.IMAGE_SELECTED,
        missing_txt_path=BARBOUR["IMAGE_MISSING_TXT"],
        verbose=True,
    )


def classify() -> None:
    from helper.image.classify_person_images import classify_images

    banner("3/3 人物 / 细节分类 → classify/person、classify/detail")
    existing = list_images(S.PERSON_DIR) + list_images(S.DETAIL_DIR)
    if existing:
        sys.exit(
            f"[停止] classify/ 下已有 {len(existing)} 张图，看起来已经分类过。\n"
            f"       重复分类会产生带前缀的重复文件。如需重跑，先清空\n"
            f"       {S.PERSON_DIR}\n       {S.DETAIL_DIR}\n"
            f"       或把 image_session.RUN_CLASSIFY 设为 False。"
        )
    classify_images(
        input_dir=S.IMAGE_SELECTED,
        person_dir=S.PERSON_DIR,
        detail_dir=S.DETAIL_DIR,
        recursive=True,
        require_head=S.CLASSIFY_REQUIRE_HEAD,
        confidence=S.CLASSIFY_CONFIDENCE,
        head_confidence=S.CLASSIFY_HEAD_CONFIDENCE,
    )


def main() -> None:
    if not read_codes(S.CODES_EXCEL):
        sys.exit(f"[停止] 找不到本批次编码：{S.CODES_EXCEL}（第一列编码，第一行表头）")

    if S.RUN_DOWNLOAD:
        download()
    if S.RUN_SELECT:
        select()
    if S.RUN_CLASSIFY:
        classify()

    person, detail = list_images(S.PERSON_DIR), list_images(S.DETAIL_DIR)
    manual_checkpoint([
        f"classify/person：{len(person)} 张 / {count_codes(person)} 款",
        f"classify/detail：{len(detail)} 张 / {count_codes(detail)} 款",
        f"缺图编码见：{BARBOUR['IMAGE_MISSING_TXT']}",
        "",
        "请翻看 classify/person，把不适合换脸的图移走：",
        "  - 还想用（不换脸直接上）的 → 移到 classify/detail，会跟细节图一起走抠图流程",
        "  - 不要的 → 直接删除",
        "完成后：image_session.FACESWAP_BATCH 选好批次，运行 step2_faceswap.py",
    ])


if __name__ == "__main__":
    main()
