# -*- coding: utf-8 -*-
"""
内存诊断脚本：跑 camper fetch 的同时，每隔 5 秒打印
  - Python 进程自身内存（RSS）
  - 所有 Chrome/chromedriver 子进程内存
  - 前 10 大 Python 对象类型（tracemalloc）

用法：python brands/camper/debug_memory.py
"""
import sys, os, threading, time, tracemalloc, gc
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psutil

# ── 启动 tracemalloc（Python 堆分配追踪）──────────────────────────────────
tracemalloc.start(10)  # 保留 10 层调用栈

_self = psutil.Process(os.getpid())
_stop = threading.Event()


def _fmt_mb(bytes_val):
    return f"{bytes_val / 1024 / 1024:.1f} MB"


def _monitor():
    snapshot_prev = None
    while not _stop.wait(5):
        gc.collect()

        # Python 进程 RSS
        py_rss = _self.memory_info().rss

        # Chrome / chromedriver 子进程（及孙进程）
        chrome_rss = 0
        chrome_count = 0
        try:
            for child in _self.children(recursive=True):
                try:
                    name = child.name().lower()
                    if "chrome" in name or "chromium" in name:
                        chrome_rss += child.memory_info().rss
                        chrome_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

        # tracemalloc top-10 类型
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("lineno")
        top = stats[:5]

        print(f"\n{'='*60}")
        print(f"[MEM] Python RSS : {_fmt_mb(py_rss)}")
        print(f"[MEM] Chrome RSS : {_fmt_mb(chrome_rss)}  ({chrome_count} 进程)")
        print(f"[MEM] 合计       : {_fmt_mb(py_rss + chrome_rss)}")

        # tracemalloc 增量（与上次快照对比）
        if snapshot_prev:
            diff = snapshot.compare_to(snapshot_prev, "lineno")
            growing = [d for d in diff if d.size_diff > 0][:5]
            if growing:
                print("[PY增量 top5]")
                for d in growing:
                    print(f"  +{_fmt_mb(d.size_diff):>8}  {d.traceback.format()[0]}")
        else:
            print("[PY top5 alloc]")
            for s in top:
                print(f"  {_fmt_mb(s.size):>8}  {s.traceback.format()[0]}")

        snapshot_prev = snapshot


monitor_thread = threading.Thread(target=_monitor, daemon=True)
monitor_thread.start()

# ── 正式跑 fetch ──────────────────────────────────────────────────────────
from brands.camper.fetch_product_info_v4 import camper_fetch_product_info

try:
    camper_fetch_product_info(max_workers=1)
finally:
    _stop.set()
    tracemalloc.stop()
