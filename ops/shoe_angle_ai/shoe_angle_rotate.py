# ops/shoe_angle_ai/shoe_angle_rotate.py
"""
鞋子产品图 — AI 视角微调/旋转 业务逻辑。

不是淘宝/鲸芽渠道业务，所以整体放在 ops/shoe_angle_ai/ 下自成一体，
不放进 common/。这个文件只放业务逻辑本身；配置在同文件夹的
shoe_angle_config.py；实际调用入口在 run_shoe_angle_rotate_urls.py /
run_shoe_angle_rotate_custom.py / legacy/run_shoe_angle_gen.py。

两条处理路径：
  process_one_sku          —— 本地图 + 自动上传 R2 + 一次生成3个角度变体
                               （legacy/run_shoe_angle_gen.py 用）
  process_one_code_rotate  —— 图片已在 R2 + 只生成 1 个角度
                               （run_shoe_angle_rotate_urls.py 用）

API 说明：
    - img_1 = img_2 = 同一张鞋子原图（双槽位强化细节保留）
    - 使用 nano-banana-2 通用图生图模型，prompt 中精确描述视角偏移
"""
import os
import io
import time
import uuid
import requests
import boto3
from botocore.exceptions import ClientError

from ops.shoe_angle_ai.shoe_angle_config import (
    SHOE_ANGLE_MODEL,
    SHOE_ANGLE_ASPECT_RATIO,
    SHOE_ANGLE_IMAGE_SIZE,
    SHOE_ANGLE_NEGATIVE_PROMPT,
    SHOE_ANGLE_VARIANTS,
    R2_ACCOUNT_ID, R2_WRITE_KEY_ID, R2_WRITE_SECRET,
    R2_BUCKET_NAME, R2_TEMP_UPLOAD_PREFIX,
)
from config import R2_PUBLIC_PREFIX  # 多条 AI 流水线共用，留在 cfg/ai_config.py


# ── R2 临时上传（仅 process_one_sku 这条本地图路径需要）──────────────────────────

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
            "R2 写入凭证未配置！请在 ops/shoe_angle_ai/shoe_angle_config.py 中填入 "
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
        prompt_hint: 来自 SHOE_ANGLE_VARIANTS 或 build_rotate_prompt_hint 的视角描述片段

    Returns:
        完整的英文 prompt 字符串
    """
    return (
        "TASK: Product Photography Angle Adjustment for E-Commerce. "
        # 图像角色说明
        # 注意：img_1/img_2 实际传的是同一张图（用来强化细节保留），之前把
        # img_2 描述成独立的"DETAIL REFERENCE"，模型容易理解成要在画面里
        # 同时呈现"主图 + 局部特写插图"这种电商常见排版，结果第二个元素
        # 渲染失败变成一团模糊的悬浮碎片。现在明确说清楚这是同一张图、
        # 只用来加强参考，不要求也不允许输出任何额外的第二个视觉元素。
        "img_1 and img_2 are the SAME reference photo of the shoe, provided twice only "
        "to reinforce accurate preservation of its exact model, color, material, logo "
        "placement, stitching pattern, sole design, and lace color. "
        "OUTPUT COMPOSITION — CRITICAL: The output must contain EXACTLY ONE (1) shoe photo "
        "and NOTHING else. Do NOT add a second inset image, zoomed detail crop, thumbnail, "
        "duplicate silhouette, floating fragment, or any secondary visual element anywhere "
        "in the canvas. A single, complete, unobstructed shoe fills the frame — no collage, "
        "no split-panel layout, no blurry ghost duplicate of any part of the shoe. "
        # 核心任务：视角偏移
        # 注意：不要写"the shoe itself does NOT move"这种话——这跟"旋转视角"
        # 的指令自相矛盾，模型很容易理解成"保持原样不动"，实测下来生成结果
        # 跟原图姿态几乎一样，只是纹理噪声不同。这里改成明确要求轮廓必须
        # 跟着变化，正面强调"这是一次真实可见的角度变化"。
        "ANGLE SHIFT INSTRUCTION: "
        f"{prompt_hint} "
        "This must be a REAL, CLEARLY VISIBLE change in viewing angle compared to img_1 — "
        "the shoe's silhouette outline, contour curvature, and the proportion of visible "
        "surfaces MUST shift accordingly. Do NOT simply reproduce the same pose as img_1 "
        "with different texture noise; the pose itself has to look different. "
        "The shoe's overall shape and proportions stay recognizable, but the viewing angle "
        "change described above must be obvious at a glance. "
        # 产品细节锁定（最高优先级）
        "PRODUCT FIDELITY — CRITICAL: "
        "Preserve EVERY product detail from img_1 with pixel-level accuracy: "
        "brand logo, wordmark, trademark labels, color panels, stitching lines, "
        "perforation patterns, lace color/texture, tongue design, heel counter shape, "
        "sole color/tread pattern, material grain (leather/suede/mesh/canvas). "
        "Do NOT alter, remove, add, or hallucinate any product feature. "
        "The shoe in the output must be instantly recognizable as THE SAME MODEL as img_1. "
        # 背景
        # 注意：光靠"不要出现XX类内容"这种抽象否定描述，实测挡不住模型偶发
        # 生成的悬浮碎片（同一张源图重跑一次可能就正常，说明是随机的生成
        # 缺陷，不是被误导）。真正有效的是把范围锁定到具体空间区域、给出
        # "拿不准就留白"的明确兜底规则，模型才会真的遵守。
        "BACKGROUND: Pure white (#FFFFFF) studio background with NO gradients, "
        "NO shadows on the background, NO floor texture. "
        "Include only a very subtle drop shadow directly beneath the shoe sole "
        "to prevent the shoe from appearing to float. "
        "SPATIAL CANVAS RULE — MANDATORY, NO EXCEPTIONS: Every pixel of the canvas that is "
        "not part of the shoe itself or its subtle contact shadow MUST be flat, pure, uniform "
        "white (#FFFFFF). This applies to the ENTIRE canvas, including all empty space above, "
        "beside, and around the shoe. Do not render anything else anywhere in the image: no "
        "extra shapes, no blurred marks, no partial objects, no faint outlines, no texture, "
        "no color variation of any kind outside the shoe itself. "
        "If you are unsure whether to render something in the empty space, leave it pure white. "
        # 输出质量
        "Output: Ultra-realistic photorealistic e-commerce product photography, "
        "2K resolution, sharp focus on the entire shoe, professional studio lighting."
    )


# ── 单 SKU 处理（本地图 + 自动上传 R2，一次生成3个角度变体）───────────────────────

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
        angle_variants: 角度定义列表，None 时使用 SHOE_ANGLE_VARIANTS
        model:          AI 模型，None 时使用默认值
        aspect_ratio:   图片比例，None 时使用默认值
        image_size:     分辨率，None 时使用默认值
        negative_prompt:负向提示词，None 时使用默认值
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


# ── 按商品编码批量旋转（图片已在 R2，不走本地上传）───────────────────────────────

def build_rotate_prompt_hint(direction: str, degrees: float) -> str:
    """构建"左转/右转 N 度"这种单角度旋转的 prompt_hint 片段。"""
    side = {
        "LEFT":  ("LEFT", "counter-clockwise horizontal camera shift", "inner side and left edge"),
        "RIGHT": ("RIGHT", "clockwise horizontal camera shift", "outer side and right edge"),
    }[direction.upper()]
    return (
        f"Rotate the shoe's viewpoint approximately {degrees:g} degrees to the {side[0]} "
        f"({side[1]}). The shoe's {side[2]} should become slightly more visible."
    )


def process_one_code_rotate(
    code: str,
    client,
    r2_prefix: str,
    output_dir: str,
    *,
    shot_suffixes: list[str],
    image_ext: str,
    azimuth_deg: float = 10.0,
    direction: str = "LEFT",
    model: str | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    negative_prompt: str | None = None,
    max_retries: int = 2,
    retry_delay: float = 8.0,
    rate_limiter=None,
    output_name_fn=None,
) -> list[str]:
    """对单个商品编码名下的多张图统一做一次视角旋转。

    图片已经在 R2 上，直接按 {r2_prefix}/{code}{suffix}{image_ext} 拼 URL，
    不做本地上传/清理（跟 process_one_sku 的本地图+上传流程是两条路）。

    Args:
        code:           商品编码
        client:         GrsAIClient 实例
        r2_prefix:      R2 图片前缀（例如 f"{R2_PUBLIC_PREFIX}/clarks"）
        output_dir:     本地输出目录（不分子文件夹，直接平铺）
        shot_suffixes:  该商品的图片后缀列表，例如 ["_1","_2","_3","_4","_5"]
        image_ext:      图片扩展名（含点），例如 ".jpg"
        azimuth_deg:    旋转角度
        direction:      "LEFT" 或 "RIGHT"
        max_retries:    每张图的最大重试次数（不含首次）
        retry_delay:    重试前等待秒数
        rate_limiter:   可选的限速器，需实现 .acquire()，每次提交 API 任务前调用
        output_name_fn: 可选，自定义输出文件名的函数，签名
                         (code, suffix, azimuth_deg, direction) -> str（含扩展名）。
                         不传时用默认命名 "{code}{suffix}_rotate{角度}{方向首字母}.png"。
                         想改命名规则时传这个参数就行，不用改这个共享函数本身。

    Returns:
        成功保存的本地文件路径列表
    """
    model           = model           or SHOE_ANGLE_MODEL
    aspect_ratio    = aspect_ratio    or SHOE_ANGLE_ASPECT_RATIO
    image_size      = image_size      or SHOE_ANGLE_IMAGE_SIZE
    negative_prompt = negative_prompt or SHOE_ANGLE_NEGATIVE_PROMPT

    prompt_hint = build_rotate_prompt_hint(direction, azimuth_deg)
    prompt = build_shoe_angle_prompt(prompt_hint)

    def _default_name(code: str, suffix: str, azimuth_deg: float, direction: str) -> str:
        return f"{code}{suffix}_rotate{azimuth_deg:g}{direction.upper()[0]}.png"

    output_name_fn = output_name_fn or _default_name

    os.makedirs(output_dir, exist_ok=True)
    saved_paths: list[str] = []

    for suffix in shot_suffixes:
        url = f"{r2_prefix.rstrip('/')}/{code}{suffix}{image_ext}"
        out_name = output_name_fn(code, suffix, azimuth_deg, direction)
        out_path = os.path.join(output_dir, out_name)

        if os.path.isfile(out_path):
            print(f"[{code}{suffix}] 已存在，跳过: {out_path}")
            saved_paths.append(out_path)
            continue

        print(f"[{code}{suffix}] 提交任务: {url}")
        result_url = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"[{code}{suffix}] 第 {attempt} 次重试（等待 {retry_delay}s）...")
                time.sleep(retry_delay)
            if rate_limiter is not None:
                rate_limiter.acquire()
            result_url = client.generate_and_wait(
                urls=[url, url],
                prompt=prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                negative_prompt=negative_prompt,
            )
            if result_url:
                break

        if not result_url:
            print(f"[{code}{suffix}] 生成失败（已重试 {max_retries} 次），跳过。")
            continue

        try:
            img_data = requests.get(result_url, timeout=60).content
            with open(out_path, "wb") as f:
                f.write(img_data)
            print(f"[{code}{suffix}] 已保存 → {out_path}")
            saved_paths.append(out_path)
        except Exception as e:
            print(f"[{code}{suffix}] 下载结果图失败: {e}")

    return saved_paths
