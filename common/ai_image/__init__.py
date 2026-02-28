"""
common.ai_image
~~~~~~~~~~~~~~~
AI 图片生成 API 客户端包。

目前支持：
- GrsAI nano-banana（模特换装 / 虚拟试穿）

用法示例：
    from common.ai_image.grsai_client import GrsAIClient
    from common.ai_image.s3_utils import create_presigned_url

"""
from common.ai_image.grsai_client import GrsAIClient
from common.ai_image.s3_utils import create_presigned_url, upload_local_file, upload_bytes_to_r2

__all__ = ["GrsAIClient", "create_presigned_url", "upload_local_file", "upload_bytes_to_r2"]
