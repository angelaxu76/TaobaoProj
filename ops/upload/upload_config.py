"""
upload_config.py — 上传自动化系统集中配置文件
修改本文件的参数即可适配不同环境，无需改动主逻辑。
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
#  目录配置
# ─────────────────────────────────────────────────────────────────

# 共享文件夹输入区（VMware 共享或 UNC 路径）
SHARED_INPUT_DIR = Path(r"\\vmware-host\Shared Folders\VMShared\input")

# 共享目录备份区：原始 Excel 在搬运到本地 processing 前，先在此留一份副本
# 按日期分子目录，避免同名文件互相覆盖；用于事后核对/问题排查/重新执行
SHARED_BACKUP_DIR = Path(r"\\vmware-host\Shared Folders\VMShared\input_backup")

# 本地处理区（从共享目录搬运到此处再处理，与共享目录完全隔离）
LOCAL_PROCESSING_DIR = Path(r"D:\RPA\processing")

# 上传失败时移入此目录（不删除，便于排查）
LOCAL_ERROR_DIR = Path(r"D:\RPA\error")

# 上传成功后是否归档到 done 目录（True=归档保留副本 / False=直接删除）
ARCHIVE_ON_SUCCESS = False
LOCAL_DONE_DIR = Path(r"D:\RPA\done")          # 仅 ARCHIVE_ON_SUCCESS=True 时有效


# ─────────────────────────────────────────────────────────────────
#  监控配置
# ─────────────────────────────────────────────────────────────────

# 监控的文件扩展名（小写）
WATCH_EXTENSIONS = (".xlsx", ".xls")

# 文件稳定性检测：文件大小连续不变多少秒才视为写入完成
STABILITY_SECONDS = 3

# 稳定性检测内部轮询间隔（秒），不建议低于 0.5
STABILITY_INTERVAL = 1.0

# 主循环扫描间隔（秒）
POLL_INTERVAL = 2.0

# 批次沉默等待时间（秒）：检测到文件后，连续 N 秒内无新文件出现才视为批次完成
# 建议设为代码生成文件的最大间隔时间 + 缓冲，例如 10 秒
BATCH_SETTLE_SECONDS = 10


# ─────────────────────────────────────────────────────────────────
#  UiPath 配置（通过 UiPath Assistant 部署的流程）
# ─────────────────────────────────────────────────────────────────

# UiRobot.exe 路径解析：
#   自动扫描以下位置（新版 UiPath 直接把 UiRobot.exe 放在 Studio 根目录下，
#   旧版则放在 Studio\<version>\ 子目录下，两种布局都要兼容）：
#     %LOCALAPPDATA%\Programs\UiPath\Studio\UiRobot.exe
#     %LOCALAPPDATA%\Programs\UiPath\Studio\*\UiRobot.exe
#     %LOCALAPPDATA%\Programs\UiPathPlatform\Studio\*\UiRobot.exe（旧目录名，兼容保留）
#     %PROGRAMFILES%\UiPath\Studio\UiRobot.exe
#     %PROGRAMFILES%\UiPath\Studio\*\UiRobot.exe
#   有多个候选时选修改时间最新的（即最后一次升级安装的版本）；均未找到时报错。
#   不再读取环境变量。

def _find_uirobot_exe() -> str:
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    search_roots = [
        Path(local_appdata) / "Programs" / "UiPath" / "Studio",
        Path(local_appdata) / "Programs" / "UiPathPlatform" / "Studio",
        Path(program_files) / "UiPath" / "Studio",
    ]

    print("[DEBUG] 自动探测 UiRobot.exe，扫描路径:")
    candidates: list[Path] = []
    for root in search_roots:
        print(f"  - {root}")
        if root.exists():
            found = [root / "UiRobot.exe"] if (root / "UiRobot.exe").exists() else []
            found.extend(root.glob("*/UiRobot.exe"))
            if found:
                candidates.extend(found)
                for f in found:
                    print(f"    [OK] 找到: {f}")
        else:
            print(f"    [X] 路径不存在")

    if not candidates:
        roots_str = "\n  - ".join(str(r) for r in search_roots)
        raise FileNotFoundError(
            "自动探测 UiRobot.exe 失败，未在标准路径下找到安装文件。\n"
            f"搜索路径:\n  - {roots_str}"
        )

    # 取修改时间最新的（= 最近一次升级安装的版本）
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    print(f"[DEBUG] 选择最新版本: {latest}")
    return str(latest)

UIPATH_ROBOT_EXE = _find_uirobot_exe()

# 已发布的流程名称（在 UiPath Assistant 里显示的名字，区分大小写）
# 对应 Orchestrator 上的 Process Name（不是 project.json 路径）
UIPATH_PROCESS_NAME = "update_stock_by_excel"

# 传给 UiPath 流程的固定 In 参数（每次调用都不变的部分）
# key = UiPath 流程里定义的 In Argument 名称（区分大小写）
# value = 对应的值
# 注意：FolderPath（处理目录）由 Python 运行时自动注入，不在这里配置
UIPATH_FIXED_ARGS = {
    # 示例：如果你的流程需要指定上传类型，可以在这里加
    "FilePath": r"D:\RPA\processing",
}

# UiPath 单次执行最长等待时间（秒），超时视为失败
# 需大于最大批次的实际处理时长（35个文件约需 10-30 分钟，建议设 2 小时保底）
UIPATH_TIMEOUT = 7200

# 调用 UiPath 前，等待上一个残留实例自然退出的最长时间（秒）
# 超时后强制 taskkill，再启动新实例；建议与 UIPATH_TIMEOUT 保持一致
UIPATH_WAIT_BEFORE_KILL_SECS = 7200

# UiPath 失败后重试次数（0=不重试）
UIPATH_RETRY_COUNT = 1

# 重试间隔（秒）
UIPATH_RETRY_INTERVAL = 5


# ─────────────────────────────────────────────────────────────────
#  日志配置
# ─────────────────────────────────────────────────────────────────

LOG_DIR = Path(r"D:\RPA\logs")
LOG_FILENAME = "upload_watcher.log"

# 单个日志文件最大体积（字节），超出后轮转
LOG_MAX_BYTES = 5 * 1024 * 1024    # 5 MB

# 保留的历史日志文件数量
LOG_BACKUP_COUNT = 3
