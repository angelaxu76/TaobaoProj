# logger_utils.py
import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logger(
    name: str = "taobao_title",
    log_dir: str = "logs/taobao_title",
    filename: str = "generate_taobao_title.log",
    max_mb: int = 20,
    backup_count: int = 10,
    level=logging.INFO
):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, filename)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 防止多次 import 重复加 handler
    if logger.handlers:
        return logger

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger
