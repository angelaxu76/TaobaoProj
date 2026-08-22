import os
import time

from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"

_LANG_NAMES = {
    "zh": "中文（简体，符合淘宝电商营销文案语气，自然流畅，不要逐字直译）",
    "en": "English",
}

_SYSTEM_PROMPT = (
    "你是一名英国服饰品牌的电商文案翻译，负责把英文商品描述/材质/卖点翻译成对应语言。"
    "要求：意译优先，符合目标语言的电商营销表达习惯，语句通顺自然；"
    "只输出翻译结果本身，不要添加任何解释、引号或前后缀。"
)


def _load_client():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠️ 未配置 DeepSeek 密钥，请设置环境变量：DEEPSEEK_API_KEY")
        return None
    try:
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    except Exception as e:
        print(f"⚠️ 初始化 DeepSeek 客户端失败：{e}")
        return None


client = _load_client()


def safe_translate(text, target_lang="ZH"):
    """
    安全翻译函数（兼容旧代码）：
    - 函数名、参数保持不变，其他脚本完全不用改
    - 改用 DeepSeek 大模型翻译，意译更自然
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
    target_name = _LANG_NAMES.get(lang, target_lang)

    if client is None:
        print("⚠️ DeepSeek 客户端未初始化成功，返回原文。")
        return text

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"翻译成{target_name}：\n{text}"},
                ],
                temperature=0.3,
                stream=False,
            )
            result = resp.choices[0].message.content.strip()
            return result if result else text
        except Exception as e:
            print(f"⚠️ DeepSeek 翻译失败：{e}")
            time.sleep(1)

    return text
