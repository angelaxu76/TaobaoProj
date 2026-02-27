"""
S3 工具：上传本地文件、生成预签名 URL。
"""
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
