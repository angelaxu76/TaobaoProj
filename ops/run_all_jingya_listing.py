# -*- coding: utf-8 -*-
"""
各品牌 prepare_jingya_listing 顺序执行总入口

用法：
  python ops/run_all_jingya_listing.py

配置：
  修改下方 CONFIG 区域来启用/禁用品牌、调整超时时间、设置重试次数。
  每个品牌在独立子进程中运行，进程退出后 Chrome 内存完全释放，避免长时间运行卡死。
  看门狗线程监控输出静默时间，超过 SILENCE_TIMEOUT_SEC 后自动 kill 并可重试。
"""

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
#  CONFIG — 修改这里来启用/禁用品牌，或调整执行顺序
# ══════════════════════════════════════════════════════════════════

BRANDS_TO_RUN = [
    "clarks",
    "camper",
    "ecco",
    "barbour",
    # "geox",
    # "marksandspencer",
]

# 某个品牌失败后是否继续跑后续品牌（True=继续，False=中止）
CONTINUE_ON_FAILURE = True

# 输出静默超过此秒数视为卡死，自动 kill（10 分钟）
SILENCE_TIMEOUT_SEC = 600

# 卡死后自动重试次数（0 = 不重试，直接标记失败）
MAX_RETRIES = 1

# 是否循环执行（True=跑完一轮后等待 LOOP_INTERVAL_SEC 再重新开始，False=只跑一次）
LOOP_ENABLED = False

# 每轮结束后等待多少秒再开始下一轮（默认 1 小时）
LOOP_INTERVAL_SEC = 3600

# ══════════════════════════════════════════════════════════════════
#  内部逻辑（不需要修改）
# ══════════════════════════════════════════════════════════════════

ROOT_DIR = Path(__file__).resolve().parent.parent

BRAND_SCRIPT_MAP = {
    "clarks":          ROOT_DIR / "brands" / "clarks"          / "pipeline" / "prepare_jingya_listing.py",
    "camper":          ROOT_DIR / "brands" / "camper"          / "pipeline" / "prepare_jingya_listing.py",
    "ecco":            ROOT_DIR / "brands" / "ecco"            / "pipeline" / "prepare_jingya_listing.py",
    "barbour":         ROOT_DIR / "brands" / "barbour"         / "pipeline" / "prepare_jingya_listing.py",
    "geox":            ROOT_DIR / "brands" / "geox"            / "pipeline" / "prepare_jingya_listing.py",
    "marksandspencer": ROOT_DIR / "brands" / "marksandspencer" / "pipeline" / "prepare_jingya_listing.py",
}


def _banner(text: str):
    line = "═" * 64
    print(f"\n{line}")
    print(f"  {text}")
    print(f"{line}", flush=True)


def _run_once(brand: str, script: Path, attempt: int) -> bool:
    """
    启动子进程运行品牌脚本，实时打印输出，并用看门狗监控静默超时。
    返回 True 表示成功（exit code 0），False 表示失败或超时被 kill。
    """
    label = f"{brand.upper()}（第 {attempt} 次）" if attempt > 1 else brand.upper()
    _banner(f"开始：{label}  [{datetime.now().strftime('%H:%M:%S')}]")

    proc = subprocess.Popen(
        [sys.executable, "-u", str(script)],  # -u 关闭输出缓冲，确保实时显示
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_output_time = [time.time()]  # 用列表使闭包可写
    killed_by_watchdog = [False]
    start_time = time.time()

    # ── 看门狗线程：检测静默超时 ──────────────────────────────────
    def watchdog():
        while proc.poll() is None:
            silence = time.time() - last_output_time[0]
            if silence >= SILENCE_TIMEOUT_SEC:
                print(
                    f"\n⏰ [{brand.upper()}] 已 {silence/60:.1f} 分钟无输出，"
                    f"判定卡死，正在 kill 进程…",
                    flush=True,
                )
                killed_by_watchdog[0] = True
                try:
                    proc.kill()
                except Exception:
                    pass
                return
            time.sleep(15)  # 每 15 秒检查一次

    wd_thread = threading.Thread(target=watchdog, daemon=True)
    wd_thread.start()

    # ── 实时读取并打印子进程输出 ───────────────────────────────────
    for line in proc.stdout:
        print(line, end="", flush=True)
        last_output_time[0] = time.time()

    proc.wait()
    wd_thread.join(timeout=5)

    elapsed = time.time() - start_time

    if killed_by_watchdog[0]:
        print(f"\n💀 {brand.upper()} 因超时被终止  ({elapsed/60:.1f} 分钟)", flush=True)
        return False

    if proc.returncode == 0:
        print(f"\n✅ {brand.upper()} 完成  ({elapsed/60:.1f} 分钟)", flush=True)
        return True

    print(f"\n❌ {brand.upper()} 失败（exit code {proc.returncode}）  ({elapsed/60:.1f} 分钟)", flush=True)
    return False


def run_brand(brand: str) -> bool:
    """带重试的品牌执行入口。"""
    script = BRAND_SCRIPT_MAP.get(brand)
    if script is None:
        print(f"⚠️  未知品牌，跳过：{brand}")
        return False
    if not script.exists():
        print(f"⚠️  脚本不存在，跳过：{script}")
        return False

    for attempt in range(1, MAX_RETRIES + 2):  # +2：1 次正常 + MAX_RETRIES 次重试
        success = _run_once(brand, script, attempt)
        if success:
            return True
        if attempt <= MAX_RETRIES:
            print(f"\n🔄 {brand.upper()} 将在 10 秒后重试（第 {attempt}/{MAX_RETRIES} 次）…", flush=True)
            time.sleep(10)

    print(f"\n⛔ {brand.upper()} 重试次数已用完，标记为失败。", flush=True)
    return False


def run_one_round(round_num: int) -> bool:
    """执行一轮所有品牌，返回是否全部成功。"""
    round_start = time.time()

    if LOOP_ENABLED:
        print(f"\n{'◆' * 64}")
        print(f"  第 {round_num} 轮开始  [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"{'◆' * 64}", flush=True)

    results: dict[str, bool] = {}

    for brand in BRANDS_TO_RUN:
        success = run_brand(brand)
        results[brand] = success

        if not success and not CONTINUE_ON_FAILURE:
            print(f"\n⛔ CONTINUE_ON_FAILURE=False，在 {brand} 失败后中止。")
            break

    # ── 本轮汇总 ──────────────────────────────────────────────────
    round_elapsed = time.time() - round_start
    round_label = f"第 {round_num} 轮完成" if LOOP_ENABLED else "全部完成"
    _banner(f"{round_label}  总耗时 {round_elapsed/60:.1f} 分钟")

    ok_brands   = [b for b, s in results.items() if s]
    fail_brands = [b for b, s in results.items() if not s]

    if ok_brands:
        print(f"  ✅ 成功：{', '.join(ok_brands)}")
    if fail_brands:
        print(f"  ❌ 失败：{', '.join(fail_brands)}")
    print()

    return len(fail_brands) == 0


def main():
    print(f"\n{'★' * 64}")
    print(f"  全品牌 Jingya Listing 流水线")
    print(f"  启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  执行品牌：{', '.join(BRANDS_TO_RUN)}")
    print(f"  静默超时：{SILENCE_TIMEOUT_SEC // 60} 分钟  |  最大重试：{MAX_RETRIES} 次")
    loop_info = f"循环模式，间隔 {LOOP_INTERVAL_SEC // 60} 分钟" if LOOP_ENABLED else "单次执行"
    print(f"  模式：{loop_info}")
    print(f"{'★' * 64}", flush=True)

    round_num = 1
    all_ok = True

    while True:
        ok = run_one_round(round_num)
        if not ok:
            all_ok = False

        if not LOOP_ENABLED:
            break

        # 循环模式：等待后进入下一轮
        next_time = datetime.fromtimestamp(time.time() + LOOP_INTERVAL_SEC)
        print(
            f"  ♻️  循环模式：等待 {LOOP_INTERVAL_SEC // 60} 分钟后开始第 {round_num + 1} 轮"
            f"（预计 {next_time.strftime('%H:%M:%S')}）",
            flush=True,
        )
        try:
            time.sleep(LOOP_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n⛔ 用户中断，退出循环。")
            break

        round_num += 1

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
