# -*- coding: utf-8 -*-
"""
Barbour 图片流水线 step2：加镜头关键字 → 上传 R2 → 换脸（只跑一轮）→ 质量对比。

男 / 女款要换不同模特，分两批跑：改 image_session.FACESWAP_BATCH 后各跑一次。
不自动重试：LinkFox 同一张图重换结果一样。linkfox_output 和 linkfox_bad 里已有的图
都算已处理，重复运行只补接口失败等没生成出来的那几张。

前置：step1 已跑完，classify/person 已人工剔除不适合换脸的图。
运行：python brands/barbour/pipeline/image/step2_faceswap.py
结束后：人工检查 linkfox_output 的换脸效果；两批都跑完后跑 step3。

本脚本把参数注入 ops/ 下的共享脚本（不修改它们），因此不依赖
ops/linkfox/_session_config.py 当前切到哪个品牌（只从那里读 API Key）。
未完成编码写在 repulibcation/faceswap_codes_{批次}.xlsx，不会动总表 codes.xlsx。
"""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root

from brands.barbour.pipeline.image import image_session as S
from brands.barbour.pipeline.image._common import (
    banner, batch_codes, list_images, manual_checkpoint, missing_shots, write_codes,
)

POINTS_PER_IMAGE = 20


def tag_shot_keyword() -> None:
    """{code}_{n} → {code}_front_{n}。add_shot_keyword 不能重复执行，这里做保护。"""
    from helper.image.add_shot_keyword import add_shot_keyword

    files = list_images(S.PERSON_DIR)
    if not files:
        sys.exit(f"[停止] classify/person 为空：{S.PERSON_DIR}，请先跑 step1。")
    marker = f"_{S.SHOT_KEYWORD}_"
    untagged = [p for p in files if marker not in p.stem]
    if not untagged:
        print(f"classify/person 已全部带 {marker} 关键字，跳过改名。")
        return
    if len(untagged) != len(files):
        names = "\n         ".join(p.name for p in untagged[:10])
        sys.exit(
            f"[停止] classify/person 里有 {len(untagged)} 张图没有 {marker}，其余已改过名。\n"
            f"       再整体改名会变成 _{S.SHOT_KEYWORD}_{S.SHOT_KEYWORD}_n，请手动把这些图改成\n"
            f"       {{code}}{marker}{{n}} 格式后重跑：\n         {names}"
        )
    banner(f"给 classify/person 的图加 {marker} 关键字")
    add_shot_keyword(str(S.PERSON_DIR), str(S.PERSON_DIR), S.SHOT_KEYWORD, dry_run=False)


def upload(codes: list[str]) -> None:
    import ops.r2_upload.upload_images_to_r2 as r2

    if not r2.R2_ACCESS_KEY_ID or not r2.R2_SECRET_ACCESS_KEY:
        sys.exit("[停止] 未设置环境变量 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY（设置后需重开终端）。")
    r2.R2_PATH_PREFIX = f"{S.R2_SHOT_SUBDIR}/"

    wanted = set(codes)
    files = [
        p for p in list_images(S.PERSON_DIR)
        if p.stem.partition("_")[0] in wanted and any(p.stem.endswith(s) for s in S.SHOT_SUFFIXES)
    ]
    banner(f"上传 {len(files)} 张原图到 R2 /{S.R2_SHOT_SUBDIR}/")
    failed = []
    with ThreadPoolExecutor(max_workers=r2.CONCURRENCY) as ex:
        futures = [ex.submit(r2.upload_one, p) for p in files]
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            if res["status"] != "success":
                failed.append(res["filename"])
            print(f"[{i}/{len(files)}] {'OK  ' if res['status'] == 'success' else 'FAIL'} {res['filename']}")
    if failed:
        sys.exit(f"[停止] {len(failed)} 张上传失败，换脸会取不到原图：{failed}")


def run_faceswap(batch: dict, pending: dict[str, set[str]], codes_xlsx: Path) -> None:
    """按"缺哪几张"分组调用换脸脚本，每款只换缺的后缀，已有结果的不重换。"""
    import ops.linkfox.run_linkfox_faceswap_direct as fs

    groups: dict[tuple[str, ...], list[str]] = {}
    for code, sfx in pending.items():
        key = tuple(s for s in S.SHOT_SUFFIXES if s in sfx)  # 保持 SHOT_SUFFIXES 顺序
        groups.setdefault(key, []).append(code)

    fs.HEADER_ROWS = 1
    fs.OUTPUT_DIR = str(S.LINKFOX_DIR)
    fs.TARGET_MODEL_URLS = list(batch["model_urls"])
    fs.R2_SHOT_SUBDIR = S.R2_SHOT_SUBDIR
    for suffixes, codes in groups.items():
        banner(f"换脸 {len(codes)} 款 × {list(suffixes)}")
        write_codes(codes_xlsx, sorted(codes))
        fs.INPUT_FILE = str(codes_xlsx)
        fs.SHOT_SUFFIXES = list(suffixes)
        fs.main()


def run_quality_check() -> None:
    from ops.ai_image.run_compare_faceswap_quality import main as compare

    Path(S.LINKFOX_DIR).mkdir(parents=True, exist_ok=True)
    compare(
        faceswap_dir=str(S.LINKFOX_DIR),
        orig_dir=str(S.PERSON_DIR),
        bad_dir=str(S.LINKFOX_BAD),
        report_csv=str(S.COMPARE_CSV),
    )


def main() -> None:
    name = S.FACESWAP_BATCH
    if name not in S.FACESWAP_BATCHES:
        sys.exit(f"[停止] FACESWAP_BATCH={name!r} 不在 FACESWAP_BATCHES 里：{list(S.FACESWAP_BATCHES)}")
    batch = S.FACESWAP_BATCHES[name]
    if not batch.get("model_urls"):
        sys.exit(f"[停止] 批次 {name} 没有配置 model_urls。")

    tag_shot_keyword()

    codes = batch_codes(S, name)
    if not codes:
        sys.exit(f"[停止] 批次 {name} 在 classify/person 里没有匹配的编码（检查 code_prefixes / codes_file）。")
    pending = missing_shots(S, codes)
    print(f"\n批次 {name}：{len(codes)} 款，其中 {len(pending)} 款还有图未换脸")

    if pending and S.RUN_UPLOAD:
        upload(sorted(pending))

    codes_xlsx = S.REPUB / f"faceswap_codes_{name}.xlsx"
    if pending:
        n_missing = sum(len(v) for v in pending.values())
        banner(f"换脸：{len(pending)} 款，缺 {n_missing} 张，预计约 {n_missing * POINTS_PER_IMAGE} 点")
        run_faceswap(batch, pending, codes_xlsx)
        banner("质量对比：衣服被改动的换脸图移到 linkfox_bad")
        run_quality_check()

    pending = missing_shots(S, codes)
    write_codes(codes_xlsx, sorted(pending))
    lines = [f"批次 {name}：{len(codes) - len(pending)}/{len(codes)} 款已处理完"]
    if pending:
        lines.append(f"仍未生成 {len(pending)} 款（接口失败等，清单：{codes_xlsx}）：")
        lines += [f"  {c}: {', '.join(sorted(v))}" for c, v in sorted(pending.items())[:20]]
        lines.append("  背影等合成失败的原因见 linkfox_output/head_failed_*.txt；需要时手动再跑一次 step2")
    lines += [
        "",
        f"请检查换脸效果：{S.LINKFOX_DIR}",
        f"  质量对比判为不合格的在 {S.LINKFOX_BAD}，请人工检查（不会自动重新生成）",
    ]
    others = [b for b in S.FACESWAP_BATCHES if b != name]
    lines.append(f"下一步：把 FACESWAP_BATCH 改成 {others} 再跑 step2；全部批次完成后跑 step3_cutout_split.py")
    manual_checkpoint(lines)


if __name__ == "__main__":
    main()
