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
    BATCH_SETTLE_SECONDS,
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

def call_uipath(folder_path: Path, logger: logging.Logger) -> bool:
    """
    通过 UiRobot.exe 调用已在 UiPath Assistant 中部署的流程。
    传入 processing 目录路径，UiPath 流程负责遍历其中的所有 Excel 文件。
    支持失败重试（由 UIPATH_RETRY_COUNT 控制）。
    返回 True = 成功，False = 最终失败。
    """
    import json

    # 动态参数：processing 目录（UiPath 流程内部循环处理其中所有文件）
    args = {"FolderPath": str(folder_path)}

    # 固定参数：从 upload_config.UIPATH_FIXED_ARGS 合并（每次调用都一样的参数）
    args.update(UIPATH_FIXED_ARGS)

    input_json = json.dumps(args, ensure_ascii=False)
    cmd = [
        UIPATH_ROBOT_EXE,
        "execute",
        "--process-name", UIPATH_PROCESS_NAME,
        "--input", input_json,
    ]

    attempts = 1 + UIPATH_RETRY_COUNT
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            logger.info(f"第 {attempt} 次重试（共 {attempts} 次）: {folder_path.name}")
            time.sleep(UIPATH_RETRY_INTERVAL)

        logger.info(f"调用 UiPath [{attempt}/{attempts}]: {folder_path.name}")

        try:
            result = subprocess.run(
                cmd,
                timeout=UIPATH_TIMEOUT,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"UiPath 执行成功: {folder_path.name}")
                return True
            else:
                logger.warning(
                    f"UiPath 返回错误码 {result.returncode}\n"
                    f"  stdout: {result.stdout.strip()}\n"
                    f"  stderr: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired:
            logger.warning(f"UiPath 超时（>{UIPATH_TIMEOUT}s）: {folder_path.name}")

        except FileNotFoundError:
            logger.error(f"找不到 UiRobot.exe，请检查配置: {UIPATH_ROBOT_EXE}")
            return False   # 可执行文件不存在，重试没有意义

        except Exception as e:
            logger.warning(f"调用 UiPath 异常: {e}")

    logger.error(f"UiPath 全部 {attempts} 次尝试均失败: {folder_path.name}")
    return False


# ─────────────────────────────────────────────────────────────────
#  成功 / 失败后处理
# ─────────────────────────────────────────────────────────────────

def handle_success(local_file: Path, logger: logging.Logger) -> None:
    """上传成功：删除或归档 processing 文件（共享目录原文件已在搬运时删除）。"""
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

def _list_shared_files() -> set[str]:
    """返回共享目录中当前所有 Excel 文件名集合（用于批次沉默检测）。"""
    try:
        return {
            f.name for f in SHARED_INPUT_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS
        }
    except OSError:
        return set()


def scan_and_process(logger: logging.Logger) -> None:
    """
    批次模式：扫描共享目录，等到连续 BATCH_SETTLE_SECONDS 秒内无新文件出现，
    视为一批文件全部就绪，再一次性搬运 + 调用 UiPath 一次批量处理。
    """
    # 1. 初次扫描，若无文件直接返回
    current_names = _list_shared_files()
    if not current_names:
        return

    logger.info(f"检测到 {len(current_names)} 个文件，等待批次完成（{BATCH_SETTLE_SECONDS}s 无新文件视为就绪）...")

    # 2. 批次沉默等待：直到连续 BATCH_SETTLE_SECONDS 内文件集合不再增加
    while True:
        time.sleep(BATCH_SETTLE_SECONDS)
        new_names = _list_shared_files()
        if new_names == current_names:
            break
        added = new_names - current_names
        logger.info(f"批次新增 {len(added)} 个文件，继续等待... 当前共 {len(new_names)} 个")
        current_names = new_names

    logger.info(f"批次就绪，共 {len(current_names)} 个文件，开始搬运")

    # 3. 稳定性检测 + 搬运所有文件
    candidates = sorted(
        (f for f in SHARED_INPUT_DIR.iterdir()
         if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS),
        key=lambda f: f.stat().st_mtime,
    )

    local_files: list[Path] = []

    for src in candidates:
        if not is_stable(src):
            logger.warning(f"文件仍在写入，跳过: {src.name}")
            continue
        try:
            local_file = copy_to_processing(src)
            logger.info(f"搬运: {src.name} → {local_file}")
            local_files.append(local_file)
            _safe_unlink(src, logger, label="共享目录")
        except OSError as e:
            logger.error(f"搬运失败，跳过: {src.name} — {e}")

    if not local_files:
        logger.warning("所有文件搬运失败，本轮跳过")
        return

    # 4. 调用 UiPath 一次，传入 processing 目录
    logger.info(f"调用 UiPath 处理 {len(local_files)} 个文件（目录: {LOCAL_PROCESSING_DIR}）")
    success = call_uipath(LOCAL_PROCESSING_DIR, logger)

    # 5. 批量处理结果
    if success:
        for local in local_files:
            handle_success(local, logger)
    else:
        for local in local_files:
            handle_failure(local, logger)


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

    # 启动时先处理 processing 目录中的残余文件
    try:
        leftover = [
            f for f in LOCAL_PROCESSING_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS
        ]
    except OSError as e:
        logger.error(f"无法读取 processing 目录: {e}")
        leftover = []

    if leftover:
        logger.info(f"发现 {len(leftover)} 个残余文件，优先处理后再监控共享目录")
        try:
            success = call_uipath(LOCAL_PROCESSING_DIR, logger)
            if success:
                for f in leftover:
                    handle_success(f, logger)
            else:
                for f in leftover:
                    handle_failure(f, logger)
        except Exception as e:
            logger.error(f"处理残余文件时发生异常: {e}", exc_info=True)
        logger.info("残余文件处理完毕，开始监控共享目录")
    else:
        logger.info("processing 目录无残余文件，直接开始监控")

    # 主监控循环：仅 KeyboardInterrupt / SystemExit 才退出，其他异常记录后继续
    while True:
        try:
            scan_and_process(logger)
        except KeyboardInterrupt:
            logger.info("收到中断信号，服务停止。")
            break
        except Exception as e:
            logger.error(f"主循环发生未预期异常，5 秒后继续: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
