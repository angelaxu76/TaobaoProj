"""
common.ai.image
~~~~~~~~~~~~~~~
AI 图片生成 API 客户端包。

目前支持：
- GrsAI nano-banana（模特换装 / 虚拟试穿）

用法示例：
    from common.ai.image import GrsAIClient
    from common.ai.image.vton_pipeline import build_image_urls, process_one
    from common.ai.image.s3_utils import create_presigned_url

"""
from common.ai.image.grsai_client import GrsAIClient
from common.ai.image.s3_utils import create_presigned_url, upload_local_file, upload_bytes_to_r2
from common.ai.image.vton_pipeline import build_image_urls, build_prompt, process_one

__all__ = [
    "GrsAIClient",
    "create_presigned_url", "upload_local_file", "upload_bytes_to_r2",
    "build_image_urls", "build_prompt", "process_one",
]
