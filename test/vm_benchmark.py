"""
VM 性能基准测试脚本
用途：量化不同虚拟机在以下维度的性能，辅助设置合理 timeout 值
  - CPU 计算速度
  - 内存带宽
  - 磁盘 I/O（读/写）
  - 数据库连接与查询延迟
  - Chrome/Selenium 启动时间
  - 网络延迟（供应商网站 + 本地 DB）

运行方法：
  python test/vm_benchmark.py
  python test/vm_benchmark.py --skip-browser  # 跳过浏览器测试（无 GUI 环境）
  python test/vm_benchmark.py --skip-db       # 跳过数据库测试
"""

import argparse
import math
import os
import platform
import socket
import struct
import sys
import tempfile
import time
import timeit
from pathlib import Path

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def section(title: str):
    width = 60
    print(f"\n{'='*width}")
    print(f"  {title}")
    print(f"{'='*width}")


def result(label: str, value: str, note: str = ""):
    line = f"  {label:<35} {value:>12}"
    if note:
        line += f"   ({note})"
    print(line)


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def fmt_sec(seconds: float) -> str:
    return f"{seconds:.2f} s"


def fmt_mb(mb: float) -> str:
    return f"{mb:.1f} MB/s"


# ---------------------------------------------------------------------------
# 系统信息
# ---------------------------------------------------------------------------

def benchmark_sysinfo():
    section("系统信息")
    import platform
    result("OS", platform.platform())
    result("Python", sys.version.split()[0])
    result("CPU 逻辑核心数", str(os.cpu_count()))
    result("主机名", socket.gethostname())

    try:
        import psutil
        mem = psutil.virtual_memory()
        result("总内存", f"{mem.total / 1024**3:.1f} GB")
        result("可用内存", f"{mem.available / 1024**3:.1f} GB")
        cpufreq = psutil.cpu_freq()
        if cpufreq:
            result("CPU 频率", f"{cpufreq.current:.0f} MHz")
    except ImportError:
        result("psutil", "未安装（跳过内存/CPU频率）", "pip install psutil")


# ---------------------------------------------------------------------------
# CPU 基准
# ---------------------------------------------------------------------------

def _cpu_workload(n: int = 500_000) -> float:
    """纯 Python 计算：求 1..n 的质数数量"""
    count = 0
    for num in range(2, n):
        if all(num % i != 0 for i in range(2, int(math.sqrt(num)) + 1)):
            count += 1
    return count


def benchmark_cpu():
    section("CPU 性能")

    # 单线程：矩阵计算（用标准库模拟）
    N = 300
    def matrix_mul():
        a = [[float(i * N + j) for j in range(N)] for i in range(N)]
        b = [[float(i + j) for j in range(N)] for i in range(N)]
        c = [[sum(a[i][k] * b[k][j] for k in range(N)) for j in range(N)] for i in range(N)]
        return c[0][0]

    t0 = time.perf_counter()
    matrix_mul()
    t1 = time.perf_counter()
    result(f"矩阵乘法 {N}x{N}（单线程）", fmt_sec(t1 - t0), "越小越好")

    # 浮点运算
    def float_ops(n=2_000_000):
        x = 1.0
        for _ in range(n):
            x = math.sqrt(x * 1.0001 + 0.0001)
        return x

    t0 = time.perf_counter()
    float_ops()
    t1 = time.perf_counter()
    result("浮点运算 200万次", fmt_sec(t1 - t0), "越小越好")

    # 字符串处理（模拟 TXT 解析）
    def string_ops(n=50_000):
        lines = [f"ProductCode: ITEM{i:05d}, Price: {i * 1.5:.2f} GBP, Size: UK{i % 15}" for i in range(n)]
        parsed = []
        for line in lines:
            parts = {k.strip(): v.strip() for k, v in (p.split(":") for p in line.split(",") if ":" in p)}
            parsed.append(parts)
        return len(parsed)

    t0 = time.perf_counter()
    string_ops()
    t1 = time.perf_counter()
    result("字符串解析 5万行", fmt_sec(t1 - t0), "模拟 TXT 商品文件解析")


# ---------------------------------------------------------------------------
# 内存带宽
# ---------------------------------------------------------------------------

def benchmark_memory():
    section("内存性能")

    SIZE = 100 * 1024 * 1024  # 100 MB

    # 写
    t0 = time.perf_counter()
    data = bytearray(SIZE)
    for i in range(0, SIZE, 4096):
        data[i] = i & 0xFF
    t1 = time.perf_counter()
    write_speed = SIZE / (t1 - t0) / 1024**2
    result("内存写入 100 MB", fmt_mb(write_speed), "越大越好")

    # 读
    t0 = time.perf_counter()
    chk = 0
    for i in range(0, SIZE, 4096):
        chk ^= data[i]
    t1 = time.perf_counter()
    read_speed = SIZE / (t1 - t0) / 1024**2
    result("内存读取 100 MB", fmt_mb(read_speed), "越大越好")
    del data


# ---------------------------------------------------------------------------
# 磁盘 I/O
# ---------------------------------------------------------------------------

def benchmark_disk(path: Path):
    section("磁盘 I/O")

    SIZE = 50 * 1024 * 1024  # 50 MB
    test_file = path / "vm_benchmark_tmp.bin"

    # 顺序写
    data = os.urandom(SIZE)
    t0 = time.perf_counter()
    with open(test_file, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    t1 = time.perf_counter()
    write_speed = SIZE / (t1 - t0) / 1024**2
    result("顺序写入 50 MB", fmt_mb(write_speed), "越大越好")

    # 顺序读
    t0 = time.perf_counter()
    with open(test_file, "rb") as f:
        _ = f.read()
    t1 = time.perf_counter()
    read_speed = SIZE / (t1 - t0) / 1024**2
    result("顺序读取 50 MB", fmt_mb(read_speed), "越大越好")

    # Excel 模拟（小文件频繁读写）
    excel_dir = path / "vm_benchmark_excels"
    excel_dir.mkdir(exist_ok=True)
    EXCEL_COUNT = 20
    t0 = time.perf_counter()
    for i in range(EXCEL_COUNT):
        fpath = excel_dir / f"test_{i:02d}.bin"
        content = os.urandom(512 * 1024)  # 512 KB per file
        with open(fpath, "wb") as f:
            f.write(content)
        with open(fpath, "rb") as f:
            _ = f.read()
    t1 = time.perf_counter()
    result(f"模拟 Excel 读写 {EXCEL_COUNT}个×512KB", fmt_sec(t1 - t0), "模拟批量 Excel 导出")

    # 清理
    test_file.unlink(missing_ok=True)
    for f in excel_dir.iterdir():
        f.unlink()
    excel_dir.rmdir()


# ---------------------------------------------------------------------------
# 网络延迟
# ---------------------------------------------------------------------------

def _tcp_ping(host: str, port: int = 80, timeout: float = 5.0) -> float | None:
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return time.perf_counter() - t0
    except Exception:
        return None


def benchmark_network():
    section("网络延迟（TCP 握手）")

    targets = [
        ("本地 PostgreSQL DB", "192.168.1.44", 5432),
        ("Barbour UK", "www.barbour.com", 443),
        ("Camper", "www.camper.com", 443),
        ("ECCO", "gb.ecco.com", 443),
        ("Clarks", "www.clarks.co.uk", 443),
        ("GEOX", "www.geox.com", 443),
        ("Cloudflare DNS", "1.1.1.1", 53),
    ]

    for label, host, port in targets:
        latency = _tcp_ping(host, port)
        if latency is None:
            result(label, "超时/不可达")
        else:
            result(label, fmt_ms(latency), "越小越好")


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------

def benchmark_db():
    section("数据库性能")
    try:
        import psycopg2
    except ImportError:
        result("psycopg2", "未安装，跳过", "pip install psycopg2-binary")
        return

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from config import PGSQL_CONFIG
        cfg = PGSQL_CONFIG.copy()
    except Exception as e:
        result("读取 PGSQL_CONFIG", f"失败：{e}")
        return

    # 连接耗时
    t0 = time.perf_counter()
    try:
        conn = psycopg2.connect(**cfg)
    except Exception as e:
        result("DB 连接", f"失败：{e}")
        return
    t1 = time.perf_counter()
    result("DB 连接建立", fmt_ms(t1 - t0), "越小越好")

    cur = conn.cursor()

    # 简单查询
    t0 = time.perf_counter()
    for _ in range(10):
        cur.execute("SELECT 1")
    t1 = time.perf_counter()
    result("SELECT 1 × 10次", fmt_ms((t1 - t0) / 10), "单次平均")

    # 数据量查询
    tables = ["camper_inventory", "barbour_inventory", "ecco_inventory"]
    for table in tables:
        try:
            t0 = time.perf_counter()
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            t1 = time.perf_counter()
            result(f"COUNT(*) {table}", fmt_ms(t1 - t0), f"{count} 行")
        except Exception:
            pass

    conn.close()


# ---------------------------------------------------------------------------
# Chrome / Selenium 启动
# ---------------------------------------------------------------------------

def benchmark_browser():
    section("浏览器启动性能")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # 尝试 undetected_chromedriver
    try:
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")

        t0 = time.perf_counter()
        driver = uc.Chrome(options=options)
        t1 = time.perf_counter()
        result("undetected Chrome 启动", fmt_sec(t1 - t0), "越小越好")

        t0 = time.perf_counter()
        driver.get("about:blank")
        t1 = time.perf_counter()
        result("首次页面加载 (about:blank)", fmt_ms(t1 - t0))

        # 加载真实页面
        t0 = time.perf_counter()
        driver.get("https://www.barbour.com/")
        t1 = time.perf_counter()
        result("加载 barbour.com", fmt_sec(t1 - t0), "实际网络条件")

        driver.quit()

    except ImportError:
        result("undetected_chromedriver", "未安装，尝试标准 selenium")

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")

            t0 = time.perf_counter()
            driver = webdriver.Chrome(options=options)
            t1 = time.perf_counter()
            result("标准 Chrome 启动", fmt_sec(t1 - t0))

            driver.quit()
        except Exception as e:
            result("Selenium", f"失败：{e}")

    except Exception as e:
        result("Chrome 启动", f"失败：{e}")


# ---------------------------------------------------------------------------
# 汇总建议
# ---------------------------------------------------------------------------

def print_summary():
    section("Timeout 设置建议参考")
    print("""
  根据各项测试结果，建议按如下思路设置 timeout：

  ┌──────────────────────────────────┬───────────────────────────────────────┐
  │ 场景                             │ 建议                                  │
  ├──────────────────────────────────┼───────────────────────────────────────┤
  │ UiPath 等待页面元素              │ Chrome启动时间 × 2 + 页面加载时间     │
  │ UiPath 等待文件生成              │ Excel写入时间 × 商品数量 + 10s 缓冲   │
  │ Selenium driver.get() timeout    │ barbour.com 加载时间 × 1.5            │
  │ DB 查询 timeout                  │ COUNT(*) 时间 × 5（保守值）           │
  │ 整体 pipeline timeout            │ 各步骤 p95 时间之和 × 1.3             │
  └──────────────────────────────────┴───────────────────────────────────────┘

  建议在【低负载】和【高负载（同时运行多个程序）】时各跑一次，
  对比结果后取高负载值作为 timeout 基准。
""")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VM 性能基准测试")
    parser.add_argument("--skip-browser", action="store_true", help="跳过浏览器测试")
    parser.add_argument("--skip-db", action="store_true", help="跳过数据库测试")
    parser.add_argument("--skip-network", action="store_true", help="跳过网络测试")
    parser.add_argument("--disk-path", default=None, help="磁盘测试目录（默认：系统临时目录）")
    args = parser.parse_args()

    disk_path = Path(args.disk_path) if args.disk_path else Path(tempfile.gettempdir())

    print(f"\n{'#'*60}")
    print(f"#  VM 性能基准测试  —  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    timings: dict[str, float] = {}

    benchmark_sysinfo()

    t = time.perf_counter()
    benchmark_cpu()
    timings["CPU"] = time.perf_counter() - t

    t = time.perf_counter()
    benchmark_memory()
    timings["内存"] = time.perf_counter() - t

    t = time.perf_counter()
    benchmark_disk(disk_path)
    timings["磁盘"] = time.perf_counter() - t

    if not args.skip_network:
        t = time.perf_counter()
        benchmark_network()
        timings["网络"] = time.perf_counter() - t

    if not args.skip_db:
        t = time.perf_counter()
        benchmark_db()
        timings["DB"] = time.perf_counter() - t

    if not args.skip_browser:
        t = time.perf_counter()
        benchmark_browser()
        timings["浏览器"] = time.perf_counter() - t

    print_summary()

    section("各模块测试耗时")
    for name, elapsed in timings.items():
        result(name, fmt_sec(elapsed))
    total = sum(timings.values())
    result("总计", fmt_sec(total))

    print(f"\n{'#'*60}\n")


if __name__ == "__main__":
    main()
