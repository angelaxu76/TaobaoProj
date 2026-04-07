"""
ops/run_pipeline.py  —  精雅上架 Pipeline 统一入口

用法（在项目根目录执行）：
    python ops/run_pipeline.py camper
    python ops/run_pipeline.py clarks ecco
    python ops/run_pipeline.py all
    python ops/run_pipeline.py --list
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────
# 配置区（只改这里）
# ────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.resolve()

LOG_DIR = Path(r"D:\temp\TaobaoPipelineLogs\TaobaoProj")

PIPELINES: dict[str, str] = {
    "camper": "brands/camper/pipeline/prepare_jingya_listing.py",
    "clarks": "brands/clarks/pipeline/prepare_jingya_listing.py",
    "ecco":   "brands/ecco/pipeline/prepare_jingya_listing.py",
    "geox":   "brands/geox/pipeline/prepare_jingya_listing.py",
}
# ────────────────────────────────────────────────


def build_env() -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    env["PYTHONUTF8"] = "1"
    return env


def run_one(brand: str, ts: str, env: dict) -> int:
    script = ROOT / PIPELINES[brand]
    if not script.exists():
        print(f"[{brand}] ❌ 脚本不存在: {script}")
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{brand}_{ts}.log"

    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  ▶  {brand.upper()}")
    print(f"     脚本: {script.relative_to(ROOT)}")
    print(f"     日志: {log_file}")
    print(sep)

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    with open(log_file, "w", encoding="utf-8") as log:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)

    proc.wait()
    rc = proc.returncode
    label = "✅ 成功" if rc == 0 else f"❌ 失败 (exit {rc})"
    print(f"\n[{brand}] {label} — 日志: {log_file}")
    return rc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行品牌精雅上架 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python ops/run_pipeline.py camper\n"
               "  python ops/run_pipeline.py clarks ecco\n"
               "  python ops/run_pipeline.py all",
    )
    parser.add_argument(
        "brands",
        nargs="*",
        metavar="BRAND",
        help=f"品牌名（{', '.join(PIPELINES)}）或 all",
    )
    parser.add_argument("--list", action="store_true", help="列出所有可用品牌")
    args = parser.parse_args()

    if args.list:
        print("可用品牌:")
        for name, path in PIPELINES.items():
            print(f"  {name:<12} {path}")
        return

    if not args.brands:
        parser.print_help()
        sys.exit(0)

    if "all" in args.brands:
        targets = list(PIPELINES)
    else:
        unknown = [b for b in args.brands if b not in PIPELINES]
        if unknown:
            print(f"未知品牌: {', '.join(unknown)}")
            print(f"可用: {', '.join(PIPELINES)}")
            sys.exit(1)
        targets = args.brands

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    env = build_env()
    results: dict[str, int] = {}

    for brand in targets:
        results[brand] = run_one(brand, ts, env)

    # ── 汇总 ──
    sep = "=" * 52
    print(f"\n{sep}")
    print("  汇总:")
    all_ok = True
    for brand, rc in results.items():
        icon = "✅" if rc == 0 else "❌"
        print(f"    {icon}  {brand}")
        if rc != 0:
            all_ok = False
    print(sep)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
