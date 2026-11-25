# -*- coding: utf-8 -*-
"""DeepSeek JSON 调用（与 common/text/translate.py 共用密钥和客户端）。"""
from __future__ import annotations

import json
import time

from common.text.translate import DEEPSEEK_MODEL, client


def available() -> bool:
    return client is not None


def chat_json(messages: list[dict], temperature: float = 1.0, retries: int = 3) -> dict | None:
    """返回解析后的 JSON 对象；失败返回 None。"""
    if client is None:
        return None
    err = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL, messages=messages, temperature=temperature,
                response_format={"type": "json_object"}, timeout=60,
            )
            data = json.loads(resp.choices[0].message.content)
            if isinstance(data, dict):
                return data
        except Exception as e:
            err = e
            time.sleep(1 + attempt)
    print(f"⚠️ DeepSeek 调用失败：{err}")
    return None
