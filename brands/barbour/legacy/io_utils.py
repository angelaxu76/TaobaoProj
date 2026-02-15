# barbour/core/io_utils.py
# -*- coding: utf-8 -*-
"""
Windows 友好的并发安全写盘：
- 原子写：临时文件 -> replace，避免半写与句柄占用
- 进程内去重：同名只写一次，避免重复线程写同一个 TXT
"""

from __future__ import annotations
import os, tempfile, time, threading
from pathlib import Path
from typing import Dict, Any, Iterable

_WRITTEN_NAMES = set()
_WRITTEN_LOCK = threading.Lock()

def atomic_write_bytes(data: bytes, dst: Path, retries: int = 3) -> bool:
    """原子写入 bytes 到 dst；已存在视为成功，不抛异常。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    for i in range(retries):
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=str(dst.parent)) as tf:
                tmp_path = Path(tf.name)
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())
            # Windows 上 Path.replace 足够原子
            tmp_path.replace(dst)
            return True
        except (PermissionError, FileExistsError):
            if dst.exists():
                return True
            time.sleep(0.2 * (i + 1))
        except Exception:
            time.sleep(0.2 * (i + 1))
        finally:
            try:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    return dst.exists()

def kv_payload(info: Dict[str, Any], fields: Iterable[str]) -> bytes:
    """把 info 的若干键转为 `key: value` 文本"""
    lines = []
    for k in fields:
        v = info.get(k, "No Data")
        lines.append(f"{k}: {v}")
    return ("\n".join(lines) + "\n").encode("utf-8", errors="ignore")

DEFAULT_FIELDS = [
    "Product Code","Product Name","Product Description","Product Gender",
    "Product Color","Product Price","Adjusted Price","Product Material",
    "Style Category","Feature","Product Size","Product Size Detail",
    "Source URL","Site Name"
]

def ensure_unique_and_write(info: Dict[str, Any], out_path: Path, fields: Iterable[str] = None) -> bool:
    """
    并发去重 + 原子写入：
    - 同名文件只写一次；已存在视为成功
    - 默认写出 KV 文本（和你们模板兼容）
    """
    name = out_path.name
    with _WRITTEN_LOCK:
        if name in _WRITTEN_NAMES:
            # 已写过本轮重复
            return True
        _WRITTEN_NAMES.add(name)

    data = kv_payload(info, fields or DEFAULT_FIELDS)
    return atomic_write_bytes(data, out_path)
