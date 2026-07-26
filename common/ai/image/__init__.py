"""
common.ai.image
~~~~~~~~~~~~~~~
AI 图片生成 API 客户端包。

目前支持：
- GrsAI nano-banana — 虚拟试穿（vton_pipeline）
- GrsAI nano-banana — 换脸+换背景（faceswap_pipeline）
- LinkFox Ziniao    — AI换模特-2.0（linkfox_faceswap_pipeline）

鞋子视角微调/旋转不是淘宝/鲸芽业务逻辑，已迁到 ops/shoe_angle_ai/
自成一体，不在这个包里，见 ops/shoe_angle_ai/shoe_angle_rotate.py。

用法示例：
    from common.ai.image import GrsAIClient, LinkFoxClient
    from common.ai.image.vton_pipeline import build_image_urls, process_one
    from common.ai.image.faceswap_pipeline import process_one_faceswap
    from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox
    from common.ai.image.s3_utils import create_presigned_url

"""
from common.ai.image.grsai_client import GrsAIClient
from common.ai.image.linkfox_client import LinkFoxClient
from common.ai.image.s3_utils import (
    create_presigned_url, upload_local_file, upload_bytes_to_r2, upload_local_file_to_r2,
)
from common.ai.image.vton_pipeline import build_image_urls, build_prompt, process_one
from common.ai.image.faceswap_pipeline import build_shot_urls, build_faceswap_prompt, process_one_faceswap
from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox

__all__ = [
    "GrsAIClient", "LinkFoxClient",
    "create_presigned_url", "upload_local_file", "upload_bytes_to_r2", "upload_local_file_to_r2",
    "build_image_urls", "build_prompt", "process_one",
    "build_shot_urls", "build_faceswap_prompt", "process_one_faceswap",
    "process_one_linkfox",
]
