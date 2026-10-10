# -*- coding: utf-8 -*-
"""
Barbour 多机抓取协作（prepare_jingya_listing.py 使用）

多台虚拟机共用共享盘上的 publication 目录，各自抓一部分供货商，
主机等全部（或超时前已就绪的）供货商 TXT 到齐后再跑 B/C/D。

文件约定（都在 PUBLICATION_BASE 下）：
  _ROUND_STARTED.json            第一台机器清空 publication 后写入，标记本轮开始时间
  {supplier}/_DONE.json          该供货商 fetch_info + 非编码过滤完成后写入
  {supplier}/_FAILED.json        该供货商 fetch_info 抛异常时写入
抓取开始前会先删掉该供货商旧的 _DONE / _FAILED 标记。
"""

import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

ROUND_FILE = "_ROUND_STARTED.json"
DONE_FILE = "_DONE.json"
FAILED_FILE = "_FAILED.json"


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_ts(path: Path) -> float | None:
    """读取标记文件里的 ts 字段；文件不存在或损坏返回 None。"""
    try:
        return float(json.loads(path.read_text(encoding="utf-8"))["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _scan_txt(txt_dir: Path) -> tuple[int, int, float]:
    """返回 (TXT 数量, 总字节数, 最新修改时间)。忽略 .done_urls.txt 这类隐藏断点文件。"""
    count = size = 0
    newest = 0.0
    try:
        with os.scandir(txt_dir) as it:
            for e in it:
                if not e.is_file() or e.name.startswith(".") or not e.name.lower().endswith(".txt"):
                    continue
                st = e.stat()
                count += 1
                size += st.st_size
                newest = max(newest, st.st_mtime)
    except FileNotFoundError:
        pass
    return count, size, newest


# ══════════════════════════════════════════════════════════════════
#  清空保护 / 本轮开始标记
# ══════════════════════════════════════════════════════════════════

def assert_no_active_crawl(publication_base: Path, guard_minutes: int) -> None:
    """
    清空 publication 前调用：任一供货商 TXT 目录在最近 guard_minutes 分钟内
    有文件写入，说明别的机器正在抓，抛 RuntimeError 拒绝清空。
    """
    if not publication_base.exists():
        return
    cutoff = time.time() - guard_minutes * 60
    for sup_dir in publication_base.iterdir():
        txt_dir = sup_dir / "TXT"
        if not txt_dir.is_dir():
            continue
        with os.scandir(txt_dir) as it:
            for e in it:
                if e.is_file() and e.stat().st_mtime >= cutoff:
                    raise RuntimeError(
                        f"{txt_dir} 在最近 {guard_minutes} 分钟内有文件写入（{e.name} @ "
                        f"{_fmt(e.stat().st_mtime)}），可能有其他机器正在抓取。"
                        f"本机应设 RUN_A_BACKUP=False。"
                    )


def mark_round_started(publication_base: Path) -> None:
    _write_json(publication_base / ROUND_FILE, {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": socket.gethostname(),
    })


# ══════════════════════════════════════════════════════════════════
#  供货商完成标记（抓取机器写）
# ══════════════════════════════════════════════════════════════════

def clear_supplier_markers(publication_base: Path, supplier: str) -> None:
    for name in (DONE_FILE, FAILED_FILE):
        (publication_base / supplier / name).unlink(missing_ok=True)


def mark_supplier_done(publication_base: Path, supplier: str, txt_dir: Path) -> int:
    count, _, _ = _scan_txt(txt_dir)
    _write_json(publication_base / supplier / DONE_FILE, {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": socket.gethostname(),
        "txt_count": count,
    })
    return count


def mark_supplier_failed(publication_base: Path, supplier: str, exc: Exception) -> None:
    _write_json(publication_base / supplier / FAILED_FILE, {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": socket.gethostname(),
        "error": f"{type(exc).__name__}: {exc}",
    })


# ══════════════════════════════════════════════════════════════════
#  主机等待
# ══════════════════════════════════════════════════════════════════

def _round_start(publication_base: Path, max_age_hours: float) -> tuple[float, str]:
    """本轮开始时间：优先取 _ROUND_STARTED.json（不超过 max_age_hours），否则回退为 now - max_age_hours。"""
    floor = time.time() - max_age_hours * 3600
    ts = _read_ts(publication_base / ROUND_FILE)
    if ts is not None and ts >= floor:
        return ts, f"本轮清空时间 {_fmt(ts)}"
    return floor, f"未找到 {max_age_hours}h 内的清空记录，只认 {_fmt(floor)} 之后的文件"


def wait_for_suppliers(
    publication_base: Path,
    txt_dirs: dict,
    suppliers: list[str],
    min_txt: dict[str, int],
    min_txt_default: int,
    stable_minutes: float,
    poll_sec: int,
    timeout_minutes: float,
    max_age_hours: float,
) -> list[str]:
    """
    轮询各供货商 TXT 目录直到全部就绪 / 失败，或超时。返回已就绪的供货商（保持传入顺序）。

    就绪 = TXT 数量 >= 门槛 且 文件晚于本轮开始 且（有本轮 _DONE.json 或 连续 stable_minutes 分钟无变化）。
    本轮 _FAILED.json 比 _DONE.json 新 → 判定失败，不再等待。
    """
    round_start, round_desc = _round_start(publication_base, max_age_hours)
    deadline = time.time() + timeout_minutes * 60
    print(f"   {round_desc}；最长等待 {timeout_minutes:.0f} 分钟（至 {_fmt(deadline)}）", flush=True)

    ready: dict[str, str] = {}
    failed: dict[str, str] = {}
    last_sig: dict[str, tuple] = {}
    stable_since: dict[str, float] = {}

    while True:
        now = time.time()
        waiting: list[str] = []

        for s in suppliers:
            if s in ready or s in failed:
                continue
            sup_dir = publication_base / s
            need = min_txt.get(s, min_txt_default)
            count, size, newest = _scan_txt(Path(txt_dirs[s]))

            done_ts = _read_ts(sup_dir / DONE_FILE)
            fail_ts = _read_ts(sup_dir / FAILED_FILE)
            done_ts = done_ts if done_ts and done_ts >= round_start else None
            fail_ts = fail_ts if fail_ts and fail_ts >= round_start else None

            if fail_ts and (done_ts is None or fail_ts > done_ts):
                failed[s] = f"抓取失败（_FAILED.json @ {_fmt(fail_ts)}），{count} 个 TXT"
                print(f"   ❌ [{s}] {failed[s]}", flush=True)
                continue
            if done_ts and count < need:
                failed[s] = f"已完成但只有 {count} 个 TXT（门槛 {need}），疑似抓取不完整"
                print(f"   ❌ [{s}] {failed[s]}", flush=True)
                continue

            sig = (count, size, newest)
            if last_sig.get(s) != sig:
                last_sig[s] = sig
                stable_since[s] = now
            stable_min = (now - stable_since[s]) / 60

            fresh = count > 0 and newest >= round_start
            if count >= need and fresh and done_ts:
                ready[s] = f"{count} 个 TXT，已完成（_DONE.json @ {_fmt(done_ts)}）"
            elif count >= need and fresh and stable_min >= stable_minutes:
                ready[s] = f"{count} 个 TXT，{stable_min:.0f} 分钟无变化（无完成标记）"
            else:
                why = "非本轮文件" if count and not fresh else f"{count}/{need} 个"
                waiting.append(f"{s}({why}, 稳定{stable_min:.0f}/{stable_minutes:g}分)")
                continue
            print(f"   ✅ [{s}] 就绪：{ready[s]}", flush=True)

        if not waiting:
            break
        if now >= deadline:
            print(f"   ⏰ 等待超时，以下供货商未就绪，B 阶段跳过：{', '.join(waiting)}", flush=True)
            break
        print(
            f"   ⏳ [{datetime.now().strftime('%H:%M:%S')}] 就绪 {len(ready)}/{len(suppliers)}"
            f"，等待中：{'  '.join(waiting)}",
            flush=True,
        )
        time.sleep(poll_sec)

    return [s for s in suppliers if s in ready]
