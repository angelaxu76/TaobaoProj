# make_manifest.py — F5 即可运行（无需命令行参数）
# 支持三种模式：
#   DEFAULT_ACTION = "generate"  生成 manifest.json
#   DEFAULT_ACTION = "check"     校验 manifest.json
#   DEFAULT_ACTION = "auto"      如果 manifest.json 存在就校验，否则生成
#
# 你只需要改这三处默认配置 ↓↓↓

from __future__ import annotations
import argparse, hashlib, json, os, sys, time, ast
from pathlib import Path

# === [F5 默认配置] ===
# 处理的目标文件（可多个）
DEFAULT_TARGETS = [
    r"barbour\common\import_uncoded_supplier_to_db_offers.py",
]
# manifest 输出/校验路径
DEFAULT_MANIFEST = r"barbour\common\manifest.json"
# 运行模式：generate / check / auto
DEFAULT_ACTION = "auto"

# === 工具函数 ===
def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def public_api(path: str) -> dict:
    """抽取函数/类签名（名称+参数个数），便于比对入口是否一致。"""
    out = {"functions": [], "classes": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                args = len([a for a in node.args.args])
                out["functions"].append({"name": node.name, "args": args})
            elif isinstance(node, ast.ClassDef):
                out["classes"].append(node.name)
    except Exception as e:
        out["error"] = f"ast_parse_failed: {e}"
    return out

def build_manifest(paths: list[str]) -> dict:
    items = []
    for p in paths:
        p = os.path.normpath(p)
        if not os.path.isfile(p):
            print(f"[SKIP] not a file: {p}")
            continue
        st = os.stat(p)
        items.append({
            "path": p.replace("\\", "/"),
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "sha256": sha256_of(p),
            "api": public_api(p),
        })
    return {"generated_at": int(time.time()), "files": items}

def write_manifest(manifest: dict, out_file: str) -> None:
    out_dir = os.path.dirname(out_file) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[WROTE] {out_file}")

def check_manifest(manifest_path: str) -> int:
    with open(manifest_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    ok = True
    for it in m.get("files", []):
        p = it["path"]
        if not os.path.isfile(p):
            print(f"[MISS] {p} not found locally")
            ok = False
            continue
        cur = sha256_of(p)
        if cur != it["sha256"]:
            print(f"[DIFF] {p}\n  expected: {it['sha256']}\n  actual  : {cur}")
            ok = False
        else:
            print(f"[OK] {p}")
    return 0 if ok else 2

# 将相对路径基于当前文件所在目录解析，方便 F5 直接跑
ROOT = Path(__file__).resolve().parent
def _abs(p: str) -> str:
    if not p:
        return ""
    q = Path(p)
    return str((q if q.is_absolute() else (ROOT / q)).resolve())

# === “无参数也能跑”的主逻辑 ===
def main() -> None:
    # 仍保留命令行用法（可选）
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--help", action="store_true")
    args, _ = ap.parse_known_args()

    # 如果用户没有通过命令行提供参数 → 走 F5 默认配置
    if (not args.paths) and (not args.check) and (not args.help):
        action = (DEFAULT_ACTION or "auto").lower()
        targets = [ _abs(p) for p in DEFAULT_TARGETS ]
        manifest_path = _abs(DEFAULT_MANIFEST)

        if action not in {"generate", "check", "auto"}:
            print(f"[ERROR] DEFAULT_ACTION should be generate/check/auto, got: {DEFAULT_ACTION}")
            sys.exit(2)

        if action == "auto":
            action = "check" if os.path.isfile(manifest_path) else "generate"

        if action == "generate":
            existing = [p for p in targets if os.path.isfile(p)]
            if not existing:
                print("[ERROR] No valid target files. Please check DEFAULT_TARGETS.")
                for p in targets:
                    print(" -", p)
                sys.exit(2)
            m = build_manifest(existing)
            write_manifest(m, manifest_path)
            return

        if action == "check":
            if not os.path.isfile(manifest_path):
                print(f"[ERROR] manifest not found: {manifest_path}")
                sys.exit(2)
            rc = check_manifest(manifest_path)
            # 为了在 VS Code 里看得清，不抛异常，打印退出码
            print(f"[DONE] check exit code = {rc}")
            sys.exit(rc)

    # 命令行常规用法（兼容原版）
    if args.help:
        print("Usage:")
        print("  python make_manifest.py file1.py [file2.py ...]   # 生成")
        print("  python make_manifest.py --check path/to/manifest.json  # 校验")
        sys.exit(0)

    if args.check:
        if not args.paths:
            print("usage: python make_manifest.py --check path/to/manifest.json")
            sys.exit(2)
        rc = check_manifest(_abs(args.paths[0]))
        sys.exit(rc)

    if not args.paths:
        print("usage: python make_manifest.py file1.py [file2.py ...]")
        sys.exit(2)

    # 生成（命令行分支）
    files = [ _abs(p) for p in args.paths ]
    m = build_manifest(files)
    # 输出到公共前缀目录，否则就放第一个文件的目录
    out_dir = os.path.commonpath(files) if len(files) > 1 else os.path.dirname(files[0])
    out_dir = out_dir if out_dir else "."
    out_file = os.path.join(out_dir, "manifest.json")
    write_manifest(m, out_file)

if __name__ == "__main__":
    main()
