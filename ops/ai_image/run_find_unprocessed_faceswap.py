"""
找出尚未完成换脸处理的商品编码，并保存到 Excel。

逻辑：
  - 扫描 ORIG_DIR，识别所有形如 {code}{suffix}.* 的原始图片
  - 扫描 FACESWAP_DIR，识别所有形如 {code}{suffix}_faceswap.* 的处理图片
  - 对每个 suffix，找出有原图但无对应换脸图的商品编码
  - 将未处理编码去重后，保存到 OUTPUT_EXCEL（列名：商品编码）

用法：
  1. 修改下方参数（SHOT_SUFFIXES 自动从 run_ai_face_swap.py 读取，无需手动同步）。
  2. python ops/ai_image/run_find_unprocessed_faceswap.py
"""
import ast
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/ai_image/
from _session_config import PERSON_DIR, FACESWAP_DIR, CODES_EXCEL

import openpyxl

# ============================================================
# 运行参数（与 run_ai_face_swap.py 保持一致）— 路径由 _session_config.py 统一管理
# ============================================================

# 原始图片所在的本地文件夹
ORIG_DIR      = str(PERSON_DIR)

# 换脸结果所在的本地文件夹
FACESWAP_DIR  = str(FACESWAP_DIR)

# 后缀列表覆盖（None = 自动从 run_ai_face_swap.py 读取，推荐保持 None）
# 只在调试或单独运行时才填写，例如：["_front_1", "_front_2"]
SHOT_SUFFIXES_OVERRIDE: list[str] | None = None

# 换脸图在原图名后追加的后缀（不含扩展名）
FACESWAP_SUFFIX = "_faceswap"

# 输出 Excel 路径 — 路径由 _session_config.py 统一管理
OUTPUT_EXCEL  = str(CODES_EXCEL)

# 支持的图片格式
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ============================================================


def _read_shot_suffixes_from_swap_script() -> list[str]:
    """用 AST 解析 run_ai_face_swap.py，提取 SHOT_SUFFIXES 的字面量值。
    不执行该脚本，安全无副作用。解析失败时返回默认值 ['_front_1']。"""
    swap_path = Path(__file__).parent / "run_ai_face_swap.py"
    if not swap_path.is_file():
        return ["_front_1"]
    try:
        tree = ast.parse(swap_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SHOT_SUFFIXES":
                        if isinstance(node.value, ast.List):
                            return [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
    except Exception:
        pass
    return ["_front_1"]


SHOT_SUFFIXES: list[str] = (
    SHOT_SUFFIXES_OVERRIDE
    if SHOT_SUFFIXES_OVERRIDE is not None
    else _read_shot_suffixes_from_swap_script()
)


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
