"""
VM 性能基准测试 — CPU / 内存 / 磁盘 I/O

运行方法：
  python test/vm_benchmark.py
  python test/vm_benchmark.py --save result_vmA.json
  python test/vm_benchmark.py --compare a.json b.json
"""

import argparse
import json
import math
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

_RESULTS: dict[str, tuple] = {}  # key -> (raw_value, unit, lower_is_better)


def section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def record(label: str, display: str, note: str = "",
           raw: float = None, unit: str = "", lower_is_better: bool = True):
    line = f"  {label:<32} {display:>12}"
    if note:
        line += f"   ({note})"
    print(line)
    if raw is not None:
        _RESULTS[label] = (raw, unit, lower_is_better)


# ---------------------------------------------------------------------------
# 系统信息
# ---------------------------------------------------------------------------

def benchmark_sysinfo() -> str:
    section("系统信息")
    import platform
    hostname = socket.gethostname()
    record("主机名", hostname)
    record("OS", platform.platform()[:40])
    record("Python", sys.version.split()[0])
    record("CPU 逻辑核心数", str(os.cpu_count()))
    try:
        import psutil
        mem = psutil.virtual_memory()
        record("总内存", f"{mem.total / 1024**3:.1f} GB")
        freq = psutil.cpu_freq()
        if freq:
            record("CPU 频率", f"{freq.current:.0f} MHz")
    except ImportError:
        record("内存/频率", "需安装 psutil", "pip install psutil")
    return hostname


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def benchmark_cpu():
    section("CPU 性能")

    # 矩阵乘法（单线程计算强度）
    N = 300
    def matrix_mul():
        a = [[float(i * N + j) for j in range(N)] for i in range(N)]
        b = [[float(i + j) for j in range(N)] for i in range(N)]
        return [[sum(a[i][k] * b[k][j] for k in range(N)) for j in range(N)] for i in range(N)]

    t0 = time.perf_counter()
    matrix_mul()
    v = time.perf_counter() - t0
    record(f"矩阵乘法 {N}×{N}（单线程）", f"{v:.2f} s", "越小越好", v, "s", True)

    # 浮点运算
    def float_ops(n=2_000_000):
        x = 1.0
        for _ in range(n):
            x = math.sqrt(x * 1.0001 + 0.0001)
        return x

    t0 = time.perf_counter()
    float_ops()
    v = time.perf_counter() - t0
    record("浮点运算 200万次", f"{v:.2f} s", "越小越好", v, "s", True)

    # 字符串解析（模拟 TXT 商品文件）
    def string_ops():
        lines = [f"ProductCode: ITEM{i:05d}, Price: {i*1.5:.2f} GBP, Size: UK{i%15}"
                 for i in range(50_000)]
        return [{k.strip(): v.strip() for k, v in (p.split(":") for p in l.split(",") if ":" in p)}
                for l in lines]

    t0 = time.perf_counter()
    string_ops()
    v = time.perf_counter() - t0
    record("字符串解析 5万行", f"{v:.2f} s", "模拟TXT解析", v, "s", True)

    # 多核并行（ThreadPoolExecutor）
    from concurrent.futures import ThreadPoolExecutor
    def workload(_):
        x = 1.0
        for _ in range(500_000):
            x = math.sqrt(x * 1.0001 + 0.0001)
        return x

    cores = os.cpu_count() or 1
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=cores) as ex:
        list(ex.map(workload, range(cores)))
    v = time.perf_counter() - t0
    record(f"多线程浮点 ×{cores}核", f"{v:.2f} s", "越小越好", v, "s", True)


# ---------------------------------------------------------------------------
# 内存
# ---------------------------------------------------------------------------

def benchmark_memory():
    section("内存性能")

    SIZE = 200 * 1024 * 1024  # 200 MB

    # 写
    t0 = time.perf_counter()
    data = bytearray(SIZE)
    for i in range(0, SIZE, 4096):
        data[i] = i & 0xFF
    v = SIZE / (time.perf_counter() - t0) / 1024**2
    record("顺序写入 200 MB", f"{v:.1f} MB/s", "越大越好", v, "MB/s", False)

    # 读
    t0 = time.perf_counter()
    chk = 0
    for i in range(0, SIZE, 4096):
        chk ^= data[i]
    v = SIZE / (time.perf_counter() - t0) / 1024**2
    record("顺序读取 200 MB", f"{v:.1f} MB/s", "越大越好", v, "MB/s", False)
    del data

    # 大量小对象分配（模拟 dict/list 处理）
    t0 = time.perf_counter()
    objs = [{"code": f"ITEM{i:05d}", "price": i * 1.5, "size": i % 15} for i in range(200_000)]
    del objs
    v = time.perf_counter() - t0
    record("20万 dict 分配+释放", f"{v:.2f} s", "越小越好", v, "s", True)


# ---------------------------------------------------------------------------
# 磁盘 I/O
# ---------------------------------------------------------------------------

def benchmark_disk(base: Path):
    section("磁盘 I/O")

    tmp = base / "_vm_bench_tmp"
    tmp.mkdir(exist_ok=True)

    # 顺序写（50 MB）
    data = os.urandom(50 * 1024 * 1024)
    fpath = tmp / "seq.bin"
    t0 = time.perf_counter()
    with open(fpath, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    v = len(data) / (time.perf_counter() - t0) / 1024**2
    record("顺序写入 50 MB", f"{v:.1f} MB/s", "越大越好", v, "MB/s", False)

    # 顺序读（50 MB）
    t0 = time.perf_counter()
    with open(fpath, "rb") as f:
        _ = f.read()
    v = len(data) / (time.perf_counter() - t0) / 1024**2
    record("顺序读取 50 MB", f"{v:.1f} MB/s", "越大越好", v, "MB/s", False)
    fpath.unlink()

    # 小文件读写（模拟 Excel 批量导出）
    COUNT, SIZE = 30, 512 * 1024
    t0 = time.perf_counter()
    for i in range(COUNT):
        p = tmp / f"f{i:02d}.bin"
        p.write_bytes(os.urandom(SIZE))
        _ = p.read_bytes()
        p.unlink()
    v = time.perf_counter() - t0
    record(f"小文件读写 {COUNT}×512KB", f"{v:.2f} s", "模拟Excel导出", v, "s", True)

    # 随机读（4KB 块，模拟碎片访问）
    big = os.urandom(10 * 1024 * 1024)
    big_path = tmp / "rand.bin"
    big_path.write_bytes(big)
    import random
    offsets = [random.randrange(0, len(big) - 4096) for _ in range(500)]
    t0 = time.perf_counter()
    with open(big_path, "rb") as f:
        for off in offsets:
            f.seek(off)
            f.read(4096)
    v = time.perf_counter() - t0
    record("随机读 4KB×500次", f"{v:.2f} s", "越小越好", v, "s", True)
    big_path.unlink()

    tmp.rmdir()


# ---------------------------------------------------------------------------
# 对比报告
# ---------------------------------------------------------------------------

def compare_results(file_a: str, file_b: str):
    with open(file_a, encoding="utf-8") as f:
        a = json.load(f)
    with open(file_b, encoding="utf-8") as f:
        b = json.load(f)

    ha, hb = a["hostname"], b["hostname"]
    COL = 14

    print(f"\n{'#'*70}")
    print(f"#  性能对比")
    print(f"#  A: {ha}  ({a['run_time']})")
    print(f"#  B: {hb}  ({b['run_time']})")
    print(f"{'#'*70}")
    print(f"\n  {'指标':<32}  {ha[:COL]:>{COL}}  {hb[:COL]:>{COL}}  {'B vs A':>8}  {'胜':>4}")
    print(f"  {'-'*80}")

    a_wins = b_wins = 0
    for key in a["results"]:
        if key not in b["results"]:
            continue
        ra = a["results"][key]
        rb = b["results"][key]
        va, vb = ra["value"], rb["value"]
        unit, lower = ra["unit"], ra["lower_is_better"]

        def fmt(v):
            if unit == "s":    return f"{v:.2f}s"
            if unit == "MB/s": return f"{v:.0f}MB/s"
            return f"{v:.2f}"

        pct = f"{(vb - va) / va * 100:+.0f}%" if va else "N/A"
        if lower:
            win = "A" if va < vb else ("B" if vb < va else "=")
        else:
            win = "A" if va > vb else ("B" if vb > va else "=")
        if win == "A": a_wins += 1
        if win == "B": b_wins += 1

        print(f"  {key:<32}  {fmt(va):>{COL}}  {fmt(vb):>{COL}}  {pct:>8}  {win:>4}")

    print(f"\n  胜出：A({ha[:12]}) {a_wins}项  |  B({hb[:12]}) {b_wins}项")
    print(f"  (B vs A: + 表示B更慢/更低，- 表示B更快/更高)\n")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VM CPU/内存/IO 性能测试")
    parser.add_argument("--disk-path", default=None, help="磁盘测试目录（默认：临时目录）")
    parser.add_argument("--save", metavar="FILE", help="保存结果到 JSON")
    parser.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"), help="对比两台机器结果")
    args = parser.parse_args()

    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return

    disk_path = Path(args.disk_path) if args.disk_path else Path(tempfile.gettempdir())
    run_time = time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'#'*55}")
    print(f"#  VM 性能基准测试  —  {run_time}")
    print(f"{'#'*55}")

    hostname = benchmark_sysinfo()
    benchmark_cpu()
    benchmark_memory()
    benchmark_disk(disk_path)

    if args.save:
        data = {
            "hostname": hostname,
            "run_time": run_time,
            "results": {k: {"value": v[0], "unit": v[1], "lower_is_better": v[2]}
                        for k, v in _RESULTS.items()},
        }
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存：{args.save}")
    else:
        print(f"\n  提示：加 --save result_{hostname}.json 可保存结果用于对比")

    print(f"\n{'#'*55}\n")


if __name__ == "__main__":
    main()
