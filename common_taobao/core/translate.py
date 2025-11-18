import os
import json
import time

from tencentcloud.common import credential
from tencentcloud.tmt.v20180321 import tmt_client, models


def _load_credentials():
    """
    从环境变量读取密钥：
      - TENCENT_SECRET_ID
      - TENCENT_SECRET_KEY
    """
    sid = os.getenv("TENCENT_SECRET_ID")
    skey = os.getenv("TENCENT_SECRET_KEY")

    if not sid or not skey:
        print("⚠️ 未配置腾讯云翻译密钥，请设置环境变量：TENCENT_SECRET_ID / TENCENT_SECRET_KEY")
        return None, None

    return sid, skey


_secret_id, _secret_key = _load_credentials()
if _secret_id and _secret_key:
    try:
        _cred = credential.Credential(_secret_id, _secret_key)
        client = tmt_client.TmtClient(_cred, "ap-hongkong")
    except Exception as e:
        print(f"⚠️ 初始化腾讯云翻译客户端失败：{e}")
        client = None
else:
    client = None


def safe_translate(text, target_lang="ZH"):
    """
    安全翻译函数（兼容旧代码）：
    - 函数名、参数保持不变，其他脚本完全不用改
    - 自动重试 3 次
    - 失败时返回原文
    """
    if not text or not text.strip():
        return ""

    lang = target_lang.lower()
    if lang in ("zh", "zh-cn", "zh_cn"):
        lang = "zh"
    elif lang in ("en", "en-us", "en-gb", "en_us", "en_gb"):
        lang = "en"

    if client is None:
        print("⚠️ 腾讯云翻译客户端未初始化成功，返回原文。")
        return text

    for _ in range(3):
        try:
            req = models.TextTranslateRequest()
            params = {
                "SourceText": text,
                "Source": "auto",
                "Target": lang,
                "ProjectId": 0,
            }
            req.from_json_string(json.dumps(params))
            resp = client.TextTranslate(req)
            time.sleep(0.2)  # ⭐⭐⭐ 限流（非常重要）
            return resp.TargetText
        except Exception as e:
            print(f"⚠️ 腾讯云翻译失败：{e}")
            time.sleep(1)

    return text
