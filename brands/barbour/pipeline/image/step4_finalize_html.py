# -*- coding: utf-8 -*-
"""
Barbour 图片流水线 step4：抠图 → 汇总 → 按优先级改名 → 生成 HTML 详情图。

  1. RUN_TAG_DETAILS   每款第一张细节图改名为 {code}_details（默认关）
  2. RUN_CUT_FACESWAP  换脸图 linkfox_output → 抠图白底正方形 → linkfox_processed
  3. RUN_CUT_DETAIL    适合抠图的 classify/detail → 抠图白底正方形 → linkfox_processed
  4. RUN_COPY_HARD     不适合抠图的 classify/detail_difficult → 原样复制到 linkfox_processed
  5. RUN_RENAME        按 IMAGE_RENAME_PRIORITY 改名为 {code}__1/__2/...（HTML 选图依赖）
  6. RUN_MERGE         合并宽图
  7. RUN_GEN_HTML      生成详情页 / 首页 HTML
  8. RUN_RENDER        渲染 PNG → 裁边

每个子步骤都能在 image_session.py 里单独开关。

运行：python brands/barbour/pipeline/image/step4_finalize_html.py
产出：repulibcation/html_cutter/{description,first_page}/
"""
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root

from cfg.brands.barbour import BARBOUR
from brands.barbour.pipeline.image import image_session as S
from brands.barbour.pipeline.image._common import banner, code_of, list_images

_NUM_SUFFIX = re.compile(r"^(?P<code>[^_]+)_(?P<n>\d+)$")


def tag_first_detail() -> None:
    """每款编号最小的细节图（detail + detail_difficult 一起看）改名为 {code}_details。"""
    groups: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    tagged = set()
    for p in list_images(S.DETAIL_DIR) + list_images(S.DETAIL_HARD_DIR):
        if p.stem.endswith("_details"):
            tagged.add(code_of(p.stem))
        m = _NUM_SUFFIX.match(p.stem)
        if m:
            groups[m["code"]].append((int(m["n"]), p))
    banner("每款第一张细节图改名为 _details")
    for code, items in sorted(groups.items()):
        if code in tagged:
            continue
        _, p = min(items)
        dst = p.with_name(f"{code}_details{p.suffix.lower()}")
        p.rename(dst)
        print(f"  {p.name} -> {dst.name}")


def _ensure_not_renamed(step: str) -> None:
    """改名后的 {code}__N 和新放进来的原始名混在一起，会让改名/选图错乱。"""
    if any("__" in p.stem for p in list_images(S.IMAGE_PROCESS)):
        sys.exit(
            f"[停止] {step}：linkfox_processed 已改名为 {{code}}__N，不能再往里加图。\n"
            f"       要重做请先清空 {S.IMAGE_PROCESS}；只想跑后面的步骤就把这一步设为 False。"
        )


def cutout(label: str, src) -> None:
    import helper.image.cut_square_white_watermark as cut

    _ensure_not_renamed(f"抠图（{label}）")
    if not list_images(src):
        print(f"[提示] {label}目录为空，跳过：{src}")
        return
    cut.AUTO_CUTOUT = S.CUT_AUTO_CUTOUT
    cut.WHITE_BG_SKIP = S.CUT_WHITE_BG_SKIP
    cut.TARGET_SIZE = S.CUT_TARGET_SIZE
    cut.FUR_CODES = S.CUT_FUR_CODES
    cut.FUR_PREFIXES = S.CUT_FUR_PREFIXES
    banner(f"抠图白底正方形：{label} → linkfox_processed")
    cut.batch_process(str(src), str(S.IMAGE_PROCESS),
                      max_workers=S.CUT_MAX_WORKERS, add_watermark=S.CUT_ADD_WATERMARK)


def copy_hard() -> None:
    _ensure_not_renamed("复制不适合抠图的图")
    hard = list_images(S.DETAIL_HARD_DIR)
    banner(f"不适合抠图的 {len(hard)} 张原样复制到 linkfox_processed")
    Path(S.IMAGE_PROCESS).mkdir(parents=True, exist_ok=True)
    for p in hard:
        dst = Path(S.IMAGE_PROCESS) / p.name
        if dst.exists():
            print(f"  [SKIP] 同名文件已存在：{p.name}")
            continue
        shutil.copy2(p, dst)


def rename_priority() -> None:
    from ops.image_rename.rename_by_shot_priority import rename_by_shot_priority

    files = list_images(S.IMAGE_PROCESS)
    if not files:
        sys.exit(f"[停止] linkfox_processed 为空：{S.IMAGE_PROCESS}")
    if any("__" in p.stem for p in files):
        print("linkfox_processed 已是 {code}__N 命名，跳过改名。")
        return
    banner("按 IMAGE_RENAME_PRIORITY 改名为 {code}__1/__2/...")
    rename_by_shot_priority(S.IMAGE_PROCESS, brand="barbour")


def merge() -> None:
    from helper.image.merge_product_images import batch_merge_images

    banner("合并宽图")
    batch_merge_images(S.IMAGE_PROCESS, BARBOUR["MERGED_DIR"], width=750)


def gen_html() -> None:
    from common.publication.generate_html import generate_html_from_codes_files
    from common.publication.generate_html_FristPage import generate_first_page_from_codes_files

    banner("生成详情页 / 首页 HTML")
    generate_html_from_codes_files("barbour", S.CODES_EXCEL, max_workers=S.HTML_MAX_WORKERS)
    generate_first_page_from_codes_files("barbour", S.CODES_EXCEL)


def render() -> None:
    from helper.html.html_to_png_multithread import convert_html_to_images
    from helper.image.trim_sides_batch import trim_sides_batch

    banner("渲染 HTML 为图片并裁边")
    convert_html_to_images(BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"], "", S.RENDER_MAX_WORKERS)
    trim_sides_batch(BARBOUR["HTML_IMAGE_DES"], BARBOUR["HTML_CUTTER_DES"])
    convert_html_to_images(BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"], "", S.RENDER_MAX_WORKERS)
    trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"], BARBOUR["HTML_CUTTER_FIRST_PAGE"])


def main() -> None:
    steps = [
        (S.RUN_TAG_DETAILS,  "1 细节图标记 _details", tag_first_detail),
        (S.RUN_CUT_FACESWAP, "2 抠图：换脸图",         lambda: cutout("换脸图", S.LINKFOX_DIR)),
        (S.RUN_CUT_DETAIL,   "3 抠图：细节图",         lambda: cutout("适合抠图的细节图", S.DETAIL_DIR)),
        (S.RUN_COPY_HARD,    "4 复制不适合抠图的图",   copy_hard),
        (S.RUN_RENAME,       "5 按优先级改名 __N",     rename_priority),
        (S.RUN_MERGE,        "6 合并宽图",             merge),
        (S.RUN_GEN_HTML,     "7 生成 HTML",            gen_html),
        (S.RUN_RENDER,       "8 渲染 + 裁边",          render),
    ]
    print("step4 本次执行：")
    for on, label, _ in steps:
        print(f"  [{'x' if on else ' '}] {label}")
    for on, _, fn in steps:
        if on:
            fn()
    print(f"\n[完成] 详情图：{BARBOUR['HTML_CUTTER_DES']}\n        首页图：{BARBOUR['HTML_CUTTER_FIRST_PAGE']}")
    print("   下一步：brands/barbour/pipeline/publish_generate_excel.py 生成发布 Excel")


if __name__ == "__main__":
    main()
