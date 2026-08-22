"""
upload_images_to_r2.py — 批量上传本地图片到 Cloudflare R2

用于把一个文件夹里的图片批量传到 R2（对象存储），保留自定义路径，
上传后 URL 形如 R2_PUBLIC_PREFIX/前缀/文件名，例如：
    https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/clarks/26185512_GW_2.webp

修改下方"配置区"参数后直接运行即可。

准备工作：
  1. R2 控制台 -> 管理 R2 API 令牌 -> 创建 API 令牌（权限选 Object Read & Write），
     生成后得到 Access Key ID / Secret Access Key。
  2. 设置环境变量 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY（设置后需重开终端）：
       setx R2_ACCESS_KEY_ID "你的access key id"
       setx R2_SECRET_ACCESS_KEY "你的secret access key"
"""
import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common.ai.image.s3_utils import upload_local_file_to_r2
from cfg.ai_config import R2_PUBLIC_PREFIX

# ─────────────────────────────────────────────────────────────────
#  配置区（每次使用前按需修改）
# ─────────────────────────────────────────────────────────────────

R2_ACCOUNT_ID = "af51016d1487afef5637f23021b4afae"   # Cloudflare Account ID
R2_BUCKET_NAME = "product-assets"  # R2 存储桶名称（与 R2_PUBLIC_PREFIX 对应的那个 bucket）

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")

# 本地图片所在文件夹（单层目录，不递归子文件夹）
LOCAL_IMAGE_DIR = Path(r"D:\TB\Products\barbour\images\person")

# 上传到 R2 后的对象 key 前缀，相当于"文件夹路径"
# 例如 "clarks/" -> 最终 key 为 "clarks/文件名.webp"
# 留空字符串则 key 就是文件名本身
R2_PATH_PREFIX = "product_front/"

# 并发上传线程数
CONCURRENCY = 8

# 参与上传的文件扩展名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# 上传结果记录
RESULT_CSV = LOCAL_IMAGE_DIR / "upload_result.csv"

# ─────────────────────────────────────────────────────────────────


def build_object_key(filename: str) -> str:
    return f"{R2_PATH_PREFIX}{filename}"


def upload_one(file_path: Path) -> dict:
    object_key = build_object_key(file_path.name)
    ok = upload_local_file_to_r2(
        local_path=str(file_path),
        object_key=object_key,
        account_id=R2_ACCOUNT_ID,
        access_key_id=R2_ACCESS_KEY_ID,
        secret_access_key=R2_SECRET_ACCESS_KEY,
        bucket_name=R2_BUCKET_NAME,
    )
    return {
        "filename": file_path.name,
        "object_key": object_key,
        "status": "success" if ok else "failed",
        "url": f"{R2_PUBLIC_PREFIX}/{object_key}" if ok else "",
    }


def main():
    if not R2_ACCOUNT_ID or not R2_BUCKET_NAME:
        print("[错误] 请先在脚本顶部配置区填写 R2_ACCOUNT_ID 和 R2_BUCKET_NAME")
        return
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print("[错误] 未读取到 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY 环境变量，请先设置后重开终端")
        return

    files = sorted(
        p for p in LOCAL_IMAGE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not files:
        print(f"[提示] {LOCAL_IMAGE_DIR} 下没有找到符合扩展名的图片")
        return

    print(f"[开始] 共 {len(files)} 张图片，并发 {CONCURRENCY}")

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(upload_one, p): p for p in files}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = "OK" if result["status"] == "success" else "FAIL"
            print(f"[{i}/{len(files)}] {status}  {result['filename']}")

    with open(RESULT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "object_key", "status", "url"])
        writer.writeheader()
        writer.writerows(results)

    ok_count = sum(1 for r in results if r["status"] == "success")
    fail_count = len(results) - ok_count
    print(f"[完成] 成功 {ok_count} / 失败 {fail_count}")
    print(f"[记录] 结果已写入 {RESULT_CSV}")


if __name__ == "__main__":
    main()
