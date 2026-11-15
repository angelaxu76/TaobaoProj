# -*- coding: utf-8 -*-
"""
Barbour 图片流水线进度检查：看各目录现状，告诉你现在该跑哪一步。只读，不改任何文件。

运行：python brands/barbour/pipeline/image/status.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root

from cfg.brands.barbour import BARBOUR
from brands.barbour.pipeline.image import image_session as S
from brands.barbour.pipeline.image._common import (
    batch_codes, count_codes, list_images, missing_shots, read_codes,
)


def _row(ok: bool, label: str, detail: str) -> None:
    print(f"  {'[OK]' if ok else '[  ]'} {label:<28}{detail}")


def _imgs(label: str, folder, recursive: bool = False) -> list[Path]:
    files = list_images(folder, recursive=recursive)
    _row(bool(files), label, f"{len(files):>5} 张 / {count_codes(files):>4} 款" if files else "空")
    return files


def main() -> None:
    print(f"\nBarbour 图片流水线进度（{S.REPUB}）\n")

    codes = read_codes(S.CODES_EXCEL)
    _row(bool(codes), "codes.xlsx", f"{len(codes):>5} 款" if codes else "缺失")
    selected = _imgs("images_selected", S.IMAGE_SELECTED, recursive=True)
    person = _imgs("classify/person", S.PERSON_DIR)
    detail = _imgs("classify/detail", S.DETAIL_DIR)

    marker = f"_{S.SHOT_KEYWORD}_"
    tagged = bool(person) and all(marker in p.stem for p in person)
    if person:
        _row(tagged, f"  已加 {marker} 关键字", "是" if tagged else "否")

    _imgs("linkfox_output", S.LINKFOX_DIR)
    pending_batches = []
    if tagged:
        for name in S.FACESWAP_BATCHES:
            bc = batch_codes(S, name)
            if not bc:
                continue
            miss = missing_shots(S, bc)
            _row(not miss, f"  换脸批次 {name}", f"{len(bc) - len(miss)}/{len(bc)} 款完成")
            if miss:
                pending_batches.append(name)

    hard_exists = Path(S.DETAIL_HARD_DIR).is_dir()
    hard = list_images(S.DETAIL_HARD_DIR)
    _row(hard_exists, "classify/detail_difficult",
         f"{len(hard):>5} 张" if hard_exists else "未拆分（step3 未跑）")

    processed = _imgs("linkfox_processed", S.IMAGE_PROCESS)
    renamed = bool(processed) and any("__" in p.stem for p in processed)
    if processed:
        _row(renamed, "  已按优先级改名 __N", "是" if renamed else "否")

    des = _imgs("html_cutter/description", BARBOUR["HTML_CUTTER_DES"])
    first = _imgs("html_cutter/first_page", BARBOUR["HTML_CUTTER_FIRST_PAGE"])

    if not codes:
        nxt = f"把本批次编码放进 {S.CODES_EXCEL}，然后跑 step1_prepare.py"
    elif not selected:
        nxt = "跑 step1_prepare.py"
    elif not person and not detail:
        nxt = "跑 step1_prepare.py（下载/选图已完成可把 RUN_DOWNLOAD / RUN_SELECT 设为 False）"
    elif person and not tagged:
        nxt = "人工剔除 classify/person 里不适合换脸的图，然后跑 step2_faceswap.py"
    elif pending_batches:
        nxt = f"FACESWAP_BATCH 设为 {pending_batches[0]!r}，跑 step2_faceswap.py（换完要人工检查效果）"
    elif not hard_exists:
        nxt = "确认换脸效果后，跑 step3_cutout_split.py"
    elif not processed:
        nxt = "人工复核 detail / detail_difficult 后，跑 step4_finalize_html.py"
    elif not renamed:
        nxt = "step4_finalize_html.py（抠图已完成：RUN_TAG_DETAILS~RUN_COPY_HARD 设为 False，从改名开始）"
    elif not des or not first:
        nxt = "step4_finalize_html.py（RUN_RENAME 及之前设为 False，从合并宽图/HTML 开始）"
    else:
        nxt = "图片已全部完成 → publish_generate_excel.py 生成发布 Excel"
    print(f"\n  >>> 下一步：{nxt}\n")


if __name__ == "__main__":
    main()
