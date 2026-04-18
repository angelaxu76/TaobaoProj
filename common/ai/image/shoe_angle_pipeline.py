"""
鞋子产品图 — AI 视角微调流水线。

功能：将本地鞋子产品图（白底棚拍）通过 GrsAI nano-banana-2 模型生成
      3 个微调视角版本（左转 5°、右转 5°、轻微俯角），所有产品细节、
      logo、材质纹理保持不变。

输入目录结构：
    shoes_input/
        SKU001/
            1.jpg
        SKU002/
            1.jpg

输出目录结构：
    shoes_output/
        SKU001/
            angle_01.png   ← 左转 5°
            angle_02.png   ← 右转 5°
            angle_03.png   ← 轻微俯角

API 说明：
    - img_1 = 鞋子原图（视角 / 姿态主参考）
    - img_2 = 鞋子原图（材质 / logo 细节副参考，与 img_1 相同）
    - 使用 nano-banana-2 通用图生图模型，prompt 中精确描述视角偏移
"""
import os
import io
import time
import uuid
import requests
import boto3
from botocore.exceptions import ClientError

from cfg.ai_config import (
    SHOE_ANGLE_MODEL,
    SHOE_ANGLE_ASPECT_RATIO,
    SHOE_ANGLE_IMAGE_SIZE,
    SHOE_ANGLE_NEGATIVE_PROMPT,
    SHOE_ANGLE_VARIANTS,
    R2_PUBLIC_PREFIX,
    R2_ACCOUNT_ID, R2_WRITE_KEY_ID, R2_WRITE_SECRET,
    R2_BUCKET_NAME, R2_TEMP_UPLOAD_PREFIX,
)


# ── R2 临时上传 ────────────────────────────────────────────────────────────────

def _upload_image_to_r2(local_path: str) -> str | None:
    """将本地图片上传至 R2 临时前缀，返回公开访问 URL。

    上传的 key 格式：{R2_TEMP_UPLOAD_PREFIX}/{uuid4}_{filename}
    调用方负责在适当时机删除（或通过 R2 生命周期规则自动过期）。

    Args:
        local_path: 本地图片路径

    Returns:
        R2 公开 URL，上传失败返回 None
    """
    if R2_ACCOUNT_ID.startswith("YOUR_"):
        raise RuntimeError(
            "R2 写入凭证未配置！请在 cfg/ai_config.py 中填入 "
            "R2_ACCOUNT_ID / R2_WRITE_KEY_ID / R2_WRITE_SECRET / R2_BUCKET_NAME。"
        )

    endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=R2_WRITE_KEY_ID,
        aws_secret_access_key=R2_WRITE_SECRET,
        region_name="auto",
    )

    filename   = os.path.basename(local_path)
    object_key = f"{R2_TEMP_UPLOAD_PREFIX}/{uuid.uuid4().hex}_{filename}"

    with open(local_path, "rb") as f:
        data = f.read()

    ext = os.path.splitext(filename)[1].lower()
    content_type = "image/png" if ext == ".png" else "image/jpeg"

    try:
        s3.upload_fileobj(
            io.BytesIO(data),
            R2_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    except ClientError as e:
        print(f"[shoe_angle] R2 上传失败: {e}")
        return None

    url = f"{R2_PUBLIC_PREFIX.rstrip('/')}/{object_key}"
    print(f"[shoe_angle] 已上传至 R2: {url}")
    return url


def _delete_r2_object(object_key: str) -> None:
    """删除 R2 上的临时对象（可选清理步骤）。"""
    if R2_ACCOUNT_ID.startswith("YOUR_"):
        return
    try:
        endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=R2_WRITE_KEY_ID,
            aws_secret_access_key=R2_WRITE_SECRET,
            region_name="auto",
        )
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
        print(f"[shoe_angle] 已清理 R2 临时文件: {object_key}")
    except Exception as e:
        print(f"[shoe_angle] 清理 R2 临时文件失败（忽略）: {e}")


# ── Prompt 构建 ────────────────────────────────────────────────────────────────

def build_shoe_angle_prompt(prompt_hint: str) -> str:
    """构建单角度的视角微调提示词。

    Args:
        prompt_hint: 来自 SHOE_ANGLE_VARIANTS 的视角描述片段

    Returns:
        完整的英文 prompt 字符串
    """
    return (
        "TASK: Product Photography Angle Adjustment for E-Commerce. "
        # 图像角色说明
        "img_1 is the MASTER REFERENCE showing the exact shoe model, color, material, "
        "logo placement, stitching pattern, sole design, lace color, and all product details. "
        "img_2 is the DETAIL REFERENCE of the same shoe — use it to reinforce texture, "
        "logo sharpness, and fine product details. "
        # 核心任务：视角偏移
        "ANGLE SHIFT INSTRUCTION: "
        f"{prompt_hint} "
        "The overall shoe silhouette, shape, and proportions must remain consistent "
        "with img_1. Only the camera viewpoint shifts slightly — the shoe itself does NOT move. "
        # 产品细节锁定（最高优先级）
        "PRODUCT FIDELITY — CRITICAL: "
        "Preserve EVERY product detail from img_1 with pixel-level accuracy: "
        "brand logo, wordmark, trademark labels, color panels, stitching lines, "
        "perforation patterns, lace color/texture, tongue design, heel counter shape, "
        "sole color/tread pattern, material grain (leather/suede/mesh/canvas). "
        "Do NOT alter, remove, add, or hallucinate any product feature. "
        "The shoe in the output must be instantly recognizable as THE SAME MODEL as img_1. "
        # 背景
        "BACKGROUND: Pure white (#FFFFFF) studio background with NO gradients, "
        "NO shadows on the background, NO floor texture. "
        "Include only a very subtle drop shadow directly beneath the shoe sole "
        "to prevent the shoe from appearing to float. "
        # 输出质量
        "Output: Ultra-realistic photorealistic e-commerce product photography, "
        "2K resolution, sharp focus on the entire shoe, professional studio lighting."
    )


# ── 单 SKU 处理 ────────────────────────────────────────────────────────────────

def process_one_sku(
    sku: str,
    input_dir: str,
    output_dir: str,
    client,
    *,
    input_filename: str = "1.jpg",
    angle_variants: list[dict] | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    negative_prompt: str | None = None,
    max_retries: int = 2,
    retry_delay: float = 5.0,
    cleanup_r2: bool = True,
) -> list[str]:
    """对单款鞋子生成 3 个角度变体图。

    Args:
        sku:            商品 SKU（对应 input_dir/<sku>/<input_filename>）
        input_dir:      输入根目录（内含 <sku>/ 子文件夹）
        output_dir:     输出根目录（结果写入 <output_dir>/<sku>/）
        client:         GrsAIClient 实例
        input_filename: SKU 文件夹内的原图文件名，默认 "1.jpg"
        angle_variants: 角度定义列表，None 时使用 cfg 的 SHOE_ANGLE_VARIANTS
        model:          AI 模型，None 时使用 cfg 默认值
        aspect_ratio:   图片比例，None 时使用 cfg 默认值
        image_size:     分辨率，None 时使用 cfg 默认值
        negative_prompt:负向提示词，None 时使用 cfg 默认值
        max_retries:    每个角度的最大重试次数（不含首次）
        retry_delay:    重试前等待秒数
        cleanup_r2:     生成完成后是否删除 R2 上的临时输入图

    Returns:
        成功保存的本地文件路径列表
    """
    angle_variants  = angle_variants  or SHOE_ANGLE_VARIANTS
    model           = model           or SHOE_ANGLE_MODEL
    aspect_ratio    = aspect_ratio    or SHOE_ANGLE_ASPECT_RATIO
    image_size      = image_size      or SHOE_ANGLE_IMAGE_SIZE
    negative_prompt = negative_prompt or SHOE_ANGLE_NEGATIVE_PROMPT

    local_input = os.path.join(input_dir, sku, input_filename)
    if not os.path.isfile(local_input):
        print(f"[{sku}] 输入图不存在，跳过: {local_input}")
        return []

    sku_output_dir = os.path.join(output_dir, sku)
    os.makedirs(sku_output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"[{sku}] 开始处理 — 输入图: {local_input}")

    # 上传输入图至 R2（获取公开 URL 供 API 使用）
    r2_url = _upload_image_to_r2(local_input)
    if not r2_url:
        print(f"[{sku}] R2 上传失败，跳过该 SKU。")
        return []

    # 从 r2_url 提取 object_key（用于后续清理）
    r2_object_key = "/".join(r2_url.split("/")[-2:])  # tmp_shoe_input/{uuid}_1.jpg
    # 更精确提取：去掉 prefix
    prefix = R2_PUBLIC_PREFIX.rstrip("/") + "/"
    r2_object_key = r2_url[len(prefix):]

    # img_1 = img_2 = 同一张鞋图（双槽位强化细节保留）
    urls = [r2_url, r2_url]

    saved_paths: list[str] = []

    try:
        for variant in angle_variants:
            label       = variant["label"]
            prompt_hint = variant["prompt_hint"]
            prompt      = build_shoe_angle_prompt(prompt_hint)

            out_filename = f"{label}.png"
            out_path     = os.path.join(sku_output_dir, out_filename)

            # 已存在则跳过
            if os.path.isfile(out_path):
                print(f"[{sku}/{label}] 已存在，跳过: {out_path}")
                saved_paths.append(out_path)
                continue

            print(f"\n[{sku}/{label}] 提交任务 ({variant['prompt_hint'][:60]}...)")

            result_url = None
            for attempt in range(max_retries + 1):
                if attempt > 0:
                    print(f"[{sku}/{label}] 第 {attempt} 次重试（等待 {retry_delay}s）...")
                    time.sleep(retry_delay)

                result_url = client.generate_and_wait(
                    urls=urls,
                    prompt=prompt,
                    model=model,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    negative_prompt=negative_prompt,
                )
                if result_url:
                    break

            if not result_url:
                print(f"[{sku}/{label}] 生成失败（已重试 {max_retries} 次），跳过。")
                continue

            # 下载并保存为 PNG
            try:
                img_data = requests.get(result_url, timeout=60).content
                with open(out_path, "wb") as f:
                    f.write(img_data)
                print(f"[{sku}/{label}] 已保存 → {out_path}")
                saved_paths.append(out_path)
            except Exception as e:
                print(f"[{sku}/{label}] 下载结果图失败: {e}")

    finally:
        # 清理 R2 临时上传
        if cleanup_r2:
            _delete_r2_object(r2_object_key)

    return saved_paths
