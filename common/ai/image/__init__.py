"""
common.ai.image
~~~~~~~~~~~~~~~
AI 图片生成 API 客户端包。

目前支持：
- GrsAI nano-banana — 虚拟试穿（vton_pipeline）
- GrsAI nano-banana — 换脸+换背景（faceswap_pipeline）
- GrsAI nano-banana — 鞋子视角微调（shoe_angle_pipeline）
- LinkFox Ziniao    — AI换模特-2.0（linkfox_faceswap_pipeline）

用法示例：
    from common.ai.image import GrsAIClient, LinkFoxClient
    from common.ai.image.vton_pipeline import build_image_urls, process_one
    from common.ai.image.faceswap_pipeline import process_one_faceswap
    from common.ai.image.shoe_angle_pipeline import process_one_sku
    from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox
    from common.ai.image.s3_utils import create_presigned_url

"""
from common.ai.image.grsai_client import GrsAIClient
from common.ai.image.linkfox_client import LinkFoxClient
from common.ai.image.s3_utils import create_presigned_url, upload_local_file, upload_bytes_to_r2
from common.ai.image.vton_pipeline import build_image_urls, build_prompt, process_one
from common.ai.image.faceswap_pipeline import build_shot_urls, build_faceswap_prompt, process_one_faceswap
from common.ai.image.shoe_angle_pipeline import build_shoe_angle_prompt, process_one_sku
from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox

__all__ = [
    "GrsAIClient", "LinkFoxClient",
    "create_presigned_url", "upload_local_file", "upload_bytes_to_r2",
    "build_image_urls", "build_prompt", "process_one",
    "build_shot_urls", "build_faceswap_prompt", "process_one_faceswap",
    "build_shoe_angle_prompt", "process_one_sku",
    "process_one_linkfox",
]
