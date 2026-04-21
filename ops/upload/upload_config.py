"""
upload_config.py — 上传自动化系统集中配置文件
修改本文件的参数即可适配不同环境，无需改动主逻辑。
"""

from pathlib import Path

# ─────────────────────────────────────────────────────────────────
#  目录配置
# ─────────────────────────────────────────────────────────────────

# 共享文件夹输入区（VMware 共享或 UNC 路径）
SHARED_INPUT_DIR = Path(r"\\vmware-host\Shared Folders\VMShared\input")

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

# UiRobot.exe 路径（Assistant 模式安装在 AppData，Studio 安装在 Program Files）
# Assistant 默认路径示例：
#   C:\Users\<你的用户名>\AppData\Local\Programs\UiPath\app-<版本号>\UiRobot.exe
# Studio 默认路径示例：
#   C:\Program Files\UiPath\Studio\UiRobot.exe
UIPATH_ROBOT_EXE = r"C:\Users\maddingxu\AppData\Local\Programs\UiPathPlatform\Studio\26.0.191-cloud.22694\UiRobot.exe"

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
UIPATH_TIMEOUT = 120

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
