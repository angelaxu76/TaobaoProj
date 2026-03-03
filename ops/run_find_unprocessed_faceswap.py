"""
找出尚未完成换脸处理的商品编码，并保存到 Excel。

逻辑：
  - 扫描 ORIG_DIR，识别所有形如 {code}{suffix}.* 的原始图片
  - 扫描 FACESWAP_DIR，识别所有形如 {code}{suffix}_faceswap.* 的处理图片
  - 对每个 suffix，找出有原图但无对应换脸图的商品编码
  - 将未处理编码去重后，保存到 OUTPUT_EXCEL（列名：商品编码）

用法：
  1. 修改下方参数（与 run_ai_face_swap.py 保持一致）。
  2. python ops/run_find_unprocessed_faceswap.py
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl

# ============================================================
# 运行参数（与 run_ai_face_swap.py 保持一致）
# ============================================================

# 原始图片所在的本地文件夹
ORIG_DIR      = r"D:\barbour\person"

# 换脸结果所在的本地文件夹
FACESWAP_DIR  = r"D:\barbour\images\ai_gen\faceswap_output"

# 要检查的后缀列表（与 run_ai_face_swap.py 中 SHOT_SUFFIXES 一致）
SHOT_SUFFIXES = ["_front_1"]

# 换脸图在原图名后追加的后缀（不含扩展名）
FACESWAP_SUFFIX = "_faceswap"

# 输出 Excel 路径（直接修改这里）
OUTPUT_EXCEL  = r"D:\barbour\unprocessed_codes.xlsx"

# 支持的图片格式
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================


def _stem_to_code_suffix(stem: str, shot_suffixes: list[str]) -> tuple[str, str] | None:
    """
    从文件 stem 中分离 code 和 suffix。
    例：'MWX0698OL71_front_1' + ['_front_1'] → ('MWX0698OL71', '_front_1')
    匹配最长的 suffix 优先（避免 _front_1 / _front_10 冲突）。
    """
    for sfx in sorted(shot_suffixes, key=len, reverse=True):
        if stem.endswith(sfx):
            code = stem[: -len(sfx)]
            if code:
                return code, sfx
    return None


def _build_set(folder: Path, shot_suffixes: list[str], strip_faceswap: bool = False) -> dict[str, set[str]]:
    """
    扫描文件夹，返回 {code: {suffix, ...}} 的字典。
    strip_faceswap=True 时，先去掉文件 stem 末尾的 FACESWAP_SUFFIX 再解析。
    """
    result: dict[str, set[str]] = {}
    for p in folder.iterdir():
        if not (p.is_file() and p.suffix.lower() in EXTS):
            continue
        stem = p.stem
        if strip_faceswap and stem.endswith(FACESWAP_SUFFIX):
            stem = stem[: -len(FACESWAP_SUFFIX)]
        parsed = _stem_to_code_suffix(stem, shot_suffixes)
        if parsed is None:
            continue
        code, sfx = parsed
        result.setdefault(code, set()).add(sfx)
    return result


def main():
    orig_dir     = Path(ORIG_DIR)
    faceswap_dir = Path(FACESWAP_DIR)

    if not orig_dir.is_dir():
        raise NotADirectoryError(f"ORIG_DIR 不存在: {orig_dir}")
    if not faceswap_dir.is_dir():
        raise NotADirectoryError(f"FACESWAP_DIR 不存在: {faceswap_dir}")

    print(f"扫描原始图片: {orig_dir}")
    orig_index = _build_set(orig_dir, SHOT_SUFFIXES, strip_faceswap=False)
    print(f"  找到 {len(orig_index)} 个商品编码（原始图）")

    print(f"扫描换脸结果: {faceswap_dir}")
    done_index = _build_set(faceswap_dir, SHOT_SUFFIXES, strip_faceswap=True)
    print(f"  找到 {len(done_index)} 个商品编码（已处理）")

    # 对每个 suffix 分别统计未处理编码
    unprocessed: set[str] = set()
    for code, orig_suffixes in orig_index.items():
        done_suffixes = done_index.get(code, set())
        missing = orig_suffixes - done_suffixes          # 有原图但无换脸图的 suffix
        if missing:
            unprocessed.add(code)

    unprocessed_sorted = sorted(unprocessed)
    print(f"\n未处理编码: {len(unprocessed_sorted)} 个（共 {len(orig_index)} 个原始编码）")

    if not unprocessed_sorted:
        print("✅ 全部已处理，无需导出。")
        return

    # 写 Excel
    out_path = Path(OUTPUT_EXCEL)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "未处理编码"
    ws.append(["商品编码"])
    for code in unprocessed_sorted:
        ws.append([code])

    # 列宽自适应
    ws.column_dimensions["A"].width = max(12, max(len(c) for c in unprocessed_sorted) + 4)

    wb.save(str(out_path))
    print(f"✅ 已保存: {out_path}")
    print(f"   共 {len(unprocessed_sorted)} 个未处理编码")


if __name__ == "__main__":
    main()
