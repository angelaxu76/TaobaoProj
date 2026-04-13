"""
file_watcher.py — 共享目录监控 + 自动上传主逻辑

流程：
  共享目录(input) → 稳定性检测 → 搬运到本地(processing)
  → 调用 UiPath 上传网页 → 成功删除 / 失败移入 error 目录

运行方式：
  python file_watcher.py
"""

import shutil
import subprocess
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 将本目录加入 sys.path，使 upload_config 可直接导入
sys.path.insert(0, str(Path(__file__).parent))

from upload_config import (
    SHARED_INPUT_DIR,
    LOCAL_PROCESSING_DIR,
    LOCAL_ERROR_DIR,
    LOCAL_DONE_DIR,
    ARCHIVE_ON_SUCCESS,
    WATCH_EXTENSIONS,
    STABILITY_SECONDS,
    STABILITY_INTERVAL,
    POLL_INTERVAL,
    DELETE_FROM_SHARED_AFTER_COPY,
    UIPATH_ROBOT_EXE,
    UIPATH_PROCESS_NAME,
    UIPATH_FIXED_ARGS,
    UIPATH_TIMEOUT,
    UIPATH_RETRY_COUNT,
    UIPATH_RETRY_INTERVAL,
    LOG_DIR,
    LOG_FILENAME,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)


# ─────────────────────────────────────────────────────────────────
#  日志
# ─────────────────────────────────────────────────────────────────

def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("upload_watcher")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        LOG_DIR / LOG_FILENAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


# ─────────────────────────────────────────────────────────────────
#  目录初始化
# ─────────────────────────────────────────────────────────────────

def ensure_dirs() -> None:
    for d in (LOCAL_PROCESSING_DIR, LOCAL_ERROR_DIR, LOCAL_DONE_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────
#  文件稳定性检测
# ─────────────────────────────────────────────────────────────────

def is_stable(file_path: Path) -> bool:
    """
    连续 STABILITY_SECONDS 秒内文件大小不变，视为写入完成。
    防止处理写入中的文件（半文件问题）。
    """
    try:
        prev_size = file_path.stat().st_size
    except OSError:
        return False

    elapsed = 0.0
    while elapsed < STABILITY_SECONDS:
        time.sleep(STABILITY_INTERVAL)
        elapsed += STABILITY_INTERVAL
        try:
            curr_size = file_path.stat().st_size
        except OSError:
            return False
        if curr_size != prev_size:
            # 文件还在变化，重置计时
            prev_size = curr_size
            elapsed = 0.0

    return True


# ─────────────────────────────────────────────────────────────────
#  文件搬运
# ─────────────────────────────────────────────────────────────────

def copy_to_processing(src: Path) -> Path:
    """
    从共享目录复制文件到本地 processing 目录。
    若同名文件已存在，自动加时间戳后缀避免覆盖。
    返回目标路径。
    """
    dest = LOCAL_PROCESSING_DIR / src.name
    if dest.exists():
        timestamp = int(time.time())
        dest = LOCAL_PROCESSING_DIR / f"{src.stem}_{timestamp}{src.suffix}"
    shutil.copy2(src, dest)
    return dest


# ─────────────────────────────────────────────────────────────────
#  UiPath 调用
# ─────────────────────────────────────────────────────────────────

def call_uipath(file_path: Path, logger: logging.Logger) -> bool:
    """
    通过 UiRobot.exe 调用已在 UiPath Assistant 中部署的流程。
    使用 --process 指定发布的流程名，而非 project.json 路径。
    支持失败重试（由 UIPATH_RETRY_COUNT 控制）。
    返回 True = 成功，False = 最终失败。
    """
    import json

    # 动态参数：文件路径（每次不同，由 Python 运行时注入）
    args = {"FilePath": str(file_path)}

    # 固定参数：从 upload_config.UIPATH_FIXED_ARGS 合并（每次调用都一样的参数）
    args.update(UIPATH_FIXED_ARGS)

    input_json = json.dumps(args, ensure_ascii=False)
    cmd = [
        UIPATH_ROBOT_EXE,
        "--process", UIPATH_PROCESS_NAME,   # 已发布的流程名（非 project.json）
        "--input", input_json,
    ]

    attempts = 1 + UIPATH_RETRY_COUNT
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            logger.info(f"第 {attempt} 次重试（共 {attempts} 次）: {file_path.name}")
            time.sleep(UIPATH_RETRY_INTERVAL)

        logger.info(f"调用 UiPath [{attempt}/{attempts}]: {file_path.name}")

        try:
            result = subprocess.run(
                cmd,
                timeout=UIPATH_TIMEOUT,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"UiPath 执行成功: {file_path.name}")
                return True
            else:
                logger.warning(
                    f"UiPath 返回错误码 {result.returncode}\n"
                    f"  stdout: {result.stdout.strip()}\n"
                    f"  stderr: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired:
            logger.warning(f"UiPath 超时（>{UIPATH_TIMEOUT}s）: {file_path.name}")

        except FileNotFoundError:
            logger.error(f"找不到 UiRobot.exe，请检查配置: {UIPATH_ROBOT_EXE}")
            return False   # 可执行文件不存在，重试没有意义

        except Exception as e:
            logger.warning(f"调用 UiPath 异常: {e}")

    logger.error(f"UiPath 全部 {attempts} 次尝试均失败: {file_path.name}")
    return False


# ─────────────────────────────────────────────────────────────────
#  成功 / 失败后处理
# ─────────────────────────────────────────────────────────────────

def handle_success(local_file: Path, shared_src: Path, logger: logging.Logger) -> None:
    """上传成功：删除或归档 processing 文件，并清理共享目录原文件。"""
    if ARCHIVE_ON_SUCCESS:
        archive_dest = LOCAL_DONE_DIR / local_file.name
        try:
            shutil.move(str(local_file), str(archive_dest))
            logger.info(f"已归档: {archive_dest}")
        except OSError as e:
            logger.warning(f"归档失败，尝试直接删除: {e}")
            _safe_unlink(local_file, logger, label="processing")
    else:
        _safe_unlink(local_file, logger, label="processing")

    if DELETE_FROM_SHARED_AFTER_COPY:
        _safe_unlink(shared_src, logger, label="共享目录")


def handle_failure(local_file: Path, logger: logging.Logger) -> None:
    """上传失败：将 processing 文件移入 error 目录，保留共享原文件供排查。"""
    error_dest = LOCAL_ERROR_DIR / local_file.name
    # 若 error 目录已有同名文件，加时间戳区分
    if error_dest.exists():
        error_dest = LOCAL_ERROR_DIR / f"{local_file.stem}_{int(time.time())}{local_file.suffix}"
    try:
        shutil.move(str(local_file), str(error_dest))
        logger.error(f"上传失败，文件已移入 error 目录: {error_dest}")
    except OSError as e:
        logger.error(f"移动到 error 目录失败: {e}")


def _safe_unlink(path: Path, logger: logging.Logger, label: str = "") -> None:
    try:
        path.unlink()
        logger.info(f"已删除{('（' + label + '）') if label else ''}: {path.name}")
    except OSError as e:
        logger.warning(f"删除失败{('（' + label + '）') if label else ''}: {path.name} — {e}")


# ─────────────────────────────────────────────────────────────────
#  主扫描逻辑（串行处理，每次扫描一批）
# ─────────────────────────────────────────────────────────────────

def scan_and_process(logger: logging.Logger) -> None:
    """
    扫描共享目录，对每个 Excel 文件依次：
      稳定性检测 → 搬运 → UiPath上传 → 成功删除 / 失败归error
    串行执行，避免并发带来的浏览器/文件锁冲突。
    """
    try:
        candidates = sorted(
            (f for f in SHARED_INPUT_DIR.iterdir()
             if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS),
            key=lambda f: f.stat().st_mtime   # 按修改时间升序，先处理旧文件
        )
    except OSError as e:
        logger.error(f"无法读取共享目录（{SHARED_INPUT_DIR}）: {e}")
        return

    if not candidates:
        return

    logger.info(f"扫描到 {len(candidates)} 个待处理文件")

    for src in candidates:
        logger.info(f"─── 处理: {src.name} ───")

        # 1. 稳定性检测
        if not is_stable(src):
            logger.warning(f"文件仍在写入，本轮跳过: {src.name}")
            continue

        # 2. 搬运到本地 processing 目录
        try:
            local_file = copy_to_processing(src)
            logger.info(f"搬运完成: {src.name} → {local_file}")
        except OSError as e:
            logger.error(f"搬运失败，跳过: {src.name} — {e}")
            continue

        # 3. 调用 UiPath 上传
        success = call_uipath(local_file, logger)

        # 4. 根据结果处理文件
        if success:
            handle_success(local_file, src, logger)
        else:
            handle_failure(local_file, logger)


# ─────────────────────────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    logger = setup_logger()
    ensure_dirs()

    logger.info("=" * 50)
    logger.info("上传监控服务启动")
    logger.info(f"  监控目录 : {SHARED_INPUT_DIR}")
    logger.info(f"  处理目录 : {LOCAL_PROCESSING_DIR}")
    logger.info(f"  错误目录 : {LOCAL_ERROR_DIR}")
    logger.info(f"  UiPath   : {UIPATH_ROBOT_EXE}")
    logger.info("=" * 50)

    try:
        while True:
            scan_and_process(logger)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("收到中断信号，服务停止。")


if __name__ == "__main__":
    main()
