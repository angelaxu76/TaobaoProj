"""
AI 模特换装示例脚本（nano-banana-pro-vt）

用法：
    直接修改下方"配置区"的路径和参数，然后运行：
        python ops/run_ai_image_generate.py

两种模式可选（改 USE_LOCAL_FILES 开关）：
    True  — 从本地上传图片到 S3，再生成预签名 URL
    False — 图片已在 S3，直接生成预签名 URL
"""
import os
import sys
import requests

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.ai_image import GrsAIClient, create_presigned_url, upload_local_file

# ============================================================
# 配置区（改这里）
# ============================================================

GRSAI_API_KEY = "你的_GRSAI_API_KEY"

# S3 配置
S3_BUCKET    = "你的_BUCKET_名称"
AWS_REGION   = "us-east-1"

# 是否从本地上传图片（True=本地路径，False=图片已在S3）
USE_LOCAL_FILES = True

# 本地图片路径（USE_LOCAL_FILES=True 时生效）
LOCAL_IMAGES = {
    "flat":   r"D:\images\flat_cloth.jpg",    # 平铺图
    "detail": r"D:\images\fabric_detail.jpg", # 面料细节图
    "model":  r"D:\images\target_model.jpg",  # 模特图
}

# S3 Key（USE_LOCAL_FILES=False 时生效，或上传后自动使用文件名）
S3_KEYS = {
    "flat":   "ai_gen/flat_cloth.jpg",
    "detail": "ai_gen/fabric_detail.jpg",
    "model":  "ai_gen/target_model.jpg",
}

# 生成参数
MODEL        = "nano-banana-pro-vt"   # 或 "nano-banana-pro-cl"
ASPECT_RATIO = "3:4"
IMAGE_SIZE   = "1K"
PROMPT = (
    "Reference image 1 is the flat garment style, "
    "image 2 is the fabric texture detail, "
    "and image 3 is the target model. "
    "Please dress the model in image 3 with the clothes from image 1, "
    "strictly following the material and pattern from image 2. "
    "High resolution, realistic fashion photography."
)

# 结果图片保存路径（留空则只打印 URL 不下载）
SAVE_PATH = r"D:\images\output\result.jpg"

# ============================================================
# 主流程
# ============================================================

def main():
    # 1. 准备 S3 Key
    s3_keys = dict(S3_KEYS)

    if USE_LOCAL_FILES:
        print("=== 上传本地图片到 S3 ===")
        for tag, local_path in LOCAL_IMAGES.items():
            key = s3_keys[tag]
            ok = upload_local_file(local_path, S3_BUCKET, key, AWS_REGION)
            if not ok:
                print(f"[ERROR] 上传失败: {local_path}")
                return

    # 2. 生成预签名 URL（顺序必须是 flat → detail → model）
    print("\n=== 生成预签名 URL ===")
    urls = []
    for tag in ("flat", "detail", "model"):
        url = create_presigned_url(S3_BUCKET, s3_keys[tag], AWS_REGION)
        if not url:
            print(f"[ERROR] 无法生成 {tag} 的预签名 URL")
            return
        print(f"  {tag}: {url[:80]}...")
        urls.append(url)

    # 3. 调用 GrsAI 生成图片
    print("\n=== 提交生图任务 ===")
    client = GrsAIClient(api_key=GRSAI_API_KEY)
    result_url = client.generate_and_wait(
        urls=urls,
        prompt=PROMPT,
        model=MODEL,
        aspect_ratio=ASPECT_RATIO,
        image_size=IMAGE_SIZE,
    )

    if not result_url:
        print("[ERROR] 生图失败，请检查上方日志")
        return

    # 4. 下载结果图片（可选）
    if SAVE_PATH:
        os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
        img_data = requests.get(result_url, timeout=60).content
        with open(SAVE_PATH, "wb") as f:
            f.write(img_data)
        print(f"\n结果已保存: {SAVE_PATH}")
    else:
        print(f"\n结果图片 URL: {result_url}")


if __name__ == "__main__":
    main()
