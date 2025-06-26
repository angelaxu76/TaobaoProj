import time
import deepl

# ✅ 替换成你的实际 DeepL API Key（已填入）
DEEPL_API_KEY = "35bb3d6c-c839-49f6-9a8f-7e00aecf24eb"
translator = deepl.Translator(DEEPL_API_KEY)

def safe_translate(text, target_lang="ZH"):
    """
    安全翻译函数，自动重试3次，如失败返回原文。
    """
    for _ in range(3):
        try:
            if not text or not text.strip():
                return ""
            return translator.translate_text(text, target_lang=target_lang).text
        except deepl.DeepLException as e:
            print(f"❌ 翻译失败: {text} → {e}")
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ 翻译异常: {text} → {e}")
            time.sleep(1)
    return text  # 如果翻译失败，返回原文
