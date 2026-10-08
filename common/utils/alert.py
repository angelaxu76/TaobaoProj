# -*- coding: utf-8 -*-
"""
alert.py
需要人工介入时的提醒工具（声音 + 邮件）。

    from common.utils.alert import notify
    notify("Cloudflare 验证", "outdoorandcountry 需要手动点验证框", key="cf_outdoor")

- 声音：播放 wav 文件（ALERT_SOUND_FILE，可按次指定 sound_file）；
        文件不存在时退化为蜂鸣。后台线程播放，不阻塞爬虫
- 邮件：使用 cfg/email_config.py 的 SMTP 账号，发送到 ALERT_RECIPIENTS
- 节流：同一个 key 在 EMAIL_THROTTLE_SECONDS 内只发一封邮件，避免刷屏
"""

from __future__ import annotations

import os
import smtplib
import socket
import threading
import time
from pathlib import Path
from email.mime.text import MIMEText
from email.header import Header

from cfg.email_config import (
    SMTP_HOST, SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, ALERT_RECIPIENTS,
)

# 项目根目录（common/utils/alert.py 往上两级），用于解析相对路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 默认提醒音（仅支持 .wav）；相对路径按项目根目录解析，随 git 同步到各虚拟机
# 留空则用蜂鸣；项目内文件不存在时退回 FALLBACK_SOUND_FILE
ALERT_SOUND_FILE = r"assets/sounds/alert.wav"
# Windows 自带可选：C:\Windows\Media\Alarm01.wav ~ Alarm10.wav、Ring01.wav ~ Ring10.wav
FALLBACK_SOUND_FILE = r"C:\Windows\Media\Alarm01.wav"

EMAIL_THROTTLE_SECONDS = 15 * 60   # 同一 key 15 分钟内最多一封邮件
SOUND_THROTTLE_SECONDS = 20        # 同一 key 20 秒内最多响一次

_lock = threading.Lock()
_last_email: dict[str, float] = {}
_last_sound: dict[str, float] = {}


def _throttled(table: dict, key: str, seconds: float) -> bool:
    """返回 True 表示仍在冷却期内（应跳过）"""
    now = time.time()
    with _lock:
        if now - table.get(key, 0) < seconds:
            return True
        table[key] = now
        return False


def _resolve_sound_path(sound_file: str | None) -> str:
    """相对路径按项目根目录解析；默认音文件不存在时退回 FALLBACK_SOUND_FILE"""
    if sound_file == "":
        return ""
    raw = ALERT_SOUND_FILE if sound_file is None else sound_file
    if not raw:
        return ""
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if sound_file is None and not p.is_file():
        return FALLBACK_SOUND_FILE
    return str(p)


def play_alarm(times: int = 3, sound_file: str | None = None,
               freq: int = 1500, duration_ms: int = 400) -> None:
    """
    后台线程播放提醒音 times 次。
    sound_file 为 None 时使用 ALERT_SOUND_FILE；传 "" 强制蜂鸣；相对路径按项目根目录解析。
    wav 文件不存在/播放失败时退化为蜂鸣，非 Windows 环境退化为终端响铃。
    """
    path = _resolve_sound_path(sound_file)

    def _run():
        try:
            import winsound
            if path and os.path.isfile(path):
                try:
                    for _ in range(times):
                        # 同步播放：一遍放完再放下一遍
                        winsound.PlaySound(path, winsound.SND_FILENAME)
                    return
                except Exception as e:
                    print(f"[alert] ⚠️ 播放 {path} 失败，改用蜂鸣: {e}")
            elif path:
                print(f"[alert] ⚠️ 提醒音文件不存在，改用蜂鸣: {path}")
            for _ in range(times):
                winsound.Beep(freq, duration_ms)
                time.sleep(0.2)
        except Exception:
            print("\a" * times, end="", flush=True)

    threading.Thread(target=_run, daemon=True).start()


def send_email(subject: str, body: str, recipients: list[str] | None = None) -> bool:
    """发送纯文本邮件，失败只打印不抛异常（提醒失败不应中断主流程）"""
    to = recipients or ALERT_RECIPIENTS
    if not to:
        print("[alert] ALERT_RECIPIENTS 为空，跳过邮件提醒")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(to)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, to, msg.as_string())
        print(f"[alert] 📧 邮件提醒已发送: {subject}")
        return True
    except Exception as e:
        print(f"[alert] ⚠️ 邮件提醒发送失败: {e}")
        return False


def notify(title: str, message: str, key: str | None = None,
           sound: bool = True, email: bool = True,
           sound_file: str | None = None) -> None:
    """
    人工介入提醒：声音 + 邮件（各自独立节流）。
    key 用于节流分组，默认等于 title。邮件在后台线程发送，不阻塞调用方。
    sound_file 可为本次提醒单独指定 wav，默认用 ALERT_SOUND_FILE。
    """
    key = key or title
    print(f"[alert] 🔔 {title}: {message}", flush=True)

    if sound and not _throttled(_last_sound, key, SOUND_THROTTLE_SECONDS):
        play_alarm(sound_file=sound_file)

    if email and not _throttled(_last_email, key, EMAIL_THROTTLE_SECONDS):
        subject = f"[TaobaoProj] {title}"
        body = (
            f"{message}\n\n"
            f"主机: {socket.gethostname()}\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        threading.Thread(target=send_email, args=(subject, body), daemon=True).start()
