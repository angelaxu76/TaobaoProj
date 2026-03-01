"""
S3 / Cloudflare R2 工具：上传文件或字节流、生成预签名 URL。

R2 与标准 S3 使用相同的 boto3 API，但需要：
  - endpoint_url: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
  - 独立的 R2 Access Key ID / Secret Access Key（在 R2 控制台创建）
  - region_name: "auto"
"""
import io
import os
import boto3
from botocore.exceptions import ClientError


def create_presigned_url(bucket_name: str, object_name: str,
                         aws_region: str = "us-east-1",
                         expiration: int = 3600) -> str | None:
    """为 S3 对象生成预签名 GET URL。

    Args:
        bucket_name:  S3 存储桶名称
        object_name:  S3 对象 Key
        aws_region:   AWS 区域，默认 us-east-1
        expiration:   URL 有效期（秒），默认 3600

    Returns:
        预签名 URL 字符串，失败时返回 None
    """
    s3 = boto3.client("s3", region_name=aws_region)
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_name},
            ExpiresIn=expiration,
        )
        return url
    except ClientError as e:
        print(f"[s3_utils] 生成预签名 URL 失败: {e}")
        return None


def upload_bytes_to_r2(
    data: bytes,
    object_key: str,
    account_id: str,
    access_key_id: str,
    secret_access_key: str,
    bucket_name: str,
    content_type: str = "image/jpeg",
) -> bool:
    """将字节流直接上传至 Cloudflare R2（无需先落本地磁盘）。

    Args:
        data:              图片字节内容
        object_key:        R2 对象 Key，如 "ai_gen/result.jpg"
        account_id:        Cloudflare Account ID
        access_key_id:     R2 Access Key ID（R2 控制台创建）
        secret_access_key: R2 Secret Access Key
        bucket_name:       R2 存储桶名称
        content_type:      MIME 类型，默认 image/jpeg

    Returns:
        成功返回 True，失败返回 False
    """
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )
    try:
        s3.upload_fileobj(
            io.BytesIO(data),
            bucket_name,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
        print(f"[r2] 上传成功: {bucket_name}/{object_key}")
        return True
    except ClientError as e:
        print(f"[r2] 上传失败: {e}")
        return False


def upload_local_file(local_path: str, bucket_name: str, object_name: str = None,
                      aws_region: str = "us-east-1") -> bool:
    """将本地文件上传至 S3。

    Args:
        local_path:   本地文件路径
        bucket_name:  目标存储桶
        object_name:  S3 Key，默认使用本地文件名
        aws_region:   AWS 区域

    Returns:
        成功返回 True，失败返回 False
    """
    if object_name is None:
        object_name = os.path.basename(local_path)
    s3 = boto3.client("s3", region_name=aws_region)
    try:
        s3.upload_file(local_path, bucket_name, object_name)
        print(f"[s3_utils] 上传成功: {local_path} -> s3://{bucket_name}/{object_name}")
        return True
    except ClientError as e:
        print(f"[s3_utils] 上传失败: {e}")
        return False
