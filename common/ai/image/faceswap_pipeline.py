"""
身份替换（Identity Swap）+ 背景替换流水线。

目标：以原始模特拍摄图为底，替换人脸/肤色/背景，服装 100% 不重绘。

img_n 槽位分配：
  img_1 = 原始拍摄图（衣服/姿态/结构底图） ← 必须
  img_2 = 目标模特脸部参考（只取脸/发型/肤色） ← 必须
  img_3 = 新背景参考图（可选，None 则生成纯净棚拍背景）

与 vton_pipeline.py 的区别：
  - vton_pipeline: 以平铺图为输入，AI 重新"穿"上衣服
  - faceswap_pipeline: 以已着装原片为输入，AI 只换脸+背景
"""
import os
import requests
from cfg.ai_config import (
    IMAGE_EXT, FACESWAP_DEFAULT_SHOT_SUFFIXES,
    FACESWAP_MODEL, FACESWAP_ASPECT_RATIO, FACESWAP_IMAGE_SIZE,
    FACESWAP_NEGATIVE_PROMPT,
    FACESWAP_FACE_DETAIL_PROMPT, FACESWAP_WHITE_BG_PROMPT,
    FACESWAP_HARDWARE_LOCK_PROMPT,
)


# ── URL 构建 ───────────────────────────────────────────────────────────────────

def build_shot_urls(
    code: str,
    r2_prefix: str,
    shot_suffixes: list[str] | None = None,
) -> list[str]:
    """根据商品编码构建原始拍摄图 URL 列表。

    Args:
        code:           商品编码，如 "MWX2343BL56"
        r2_prefix:      R2 公共访问前缀
        shot_suffixes:  后缀列表，如 ["_1"] 或 ["_1", "_5"]；
                        None 时使用 cfg 的 FACESWAP_DEFAULT_SHOT_SUFFIXES

    Returns:
        URL 列表，顺序对应 shot_suffixes
    """
    if shot_suffixes is None:
        shot_suffixes = FACESWAP_DEFAULT_SHOT_SUFFIXES
    base = r2_prefix.rstrip("/")
    return [f"{base}/{code}{s}{IMAGE_EXT}" for s in shot_suffixes]


# ── Prompt 构建 ───────────────────────────────────────────────────────────────

def build_faceswap_prompt(has_bg_ref: bool = False) -> str:
    """构建身份替换专用提示词。

    Args:
        has_bg_ref: True 时 img_3 为背景参考图，False 时生成纯净棚拍背景
    """
    bg_clause = (
        "ABSOLUTELY DISCARD the original background from img_1. "
        "Replace it with a background IDENTICAL to img_3. "
        "Match the pure white pixels of img_3 exactly so the final background is clipped white (#FFFFFF) "
        "with no gray cast, no texture, and no environment residue."
        if has_bg_ref
        else FACESWAP_WHITE_BG_PROMPT
    )
    return (
        "TASK: High-Fidelity Identity & Background Replacement. "
        "img_1 is the ABSOLUTE MASTER BASE IMAGE — it contains the real garment, "
        "real pose, and real garment structure that MUST be preserved without any change. "
        "img_2 is the IDENTITY REFERENCE — use ONLY its face, hair, and skin tone. "
        # 身份替换
        "1. Identity Swap: Replace ONLY the face, hair, neck skin, and visible skin areas "
        "(hands, wrists) from img_1 with the facial identity and skin tone of img_2. "
        "The replaced face must match the original head position and angle from img_1. "
        "Blend seamlessly at the neckline and wrist edges. "
        # 服装锁定（核心）
        "2. Garment Lock — CRITICAL: The clothing from img_1 is SACRED and MUST NOT be "
        "re-generated, redrawn, or altered in ANY way. "
        "Preserve every stitch, fold, crease, button, zipper, pocket, and fabric texture "
        "from img_1 with pixel-level accuracy. "
        "Do NOT add, remove, or modify any garment detail. "
        "Do NOT change any colors, patterns, or color-blocking on the garment. "
        "If the garment has asymmetric color design, preserve it exactly as shown in img_1. "
        # 背景替换
        # 姿态锁定
        "3. Pose & Body: Keep the exact body pose, proportions, and limb positions "
        "from img_1 unchanged. "
        f"4. Face Realism: {FACESWAP_FACE_DETAIL_PROMPT} "
        f"5. Hardware & Zipper Lock: {FACESWAP_HARDWARE_LOCK_PROMPT} "
        f"6. Background: {bg_clause} "
        # 输出质量
        "Output: Ultra-realistic, photorealistic seamless blending, "
        "8K resolution, e-commerce standard."
    )


# ── 单款处理 ──────────────────────────────────────────────────────────────────

def process_one_faceswap(
    code: str,
    client,
    r2_prefix: str,
    output_dir: str,
    *,
    target_face_url: str,
    shot_suffixes: list[str] | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    negative_prompt: str | None = None,
    background_url: str | None = None,
) -> list[str]:
    """对单款商品执行批量换脸+换背景，每张原图生成一张结果。

    Args:
        code:             商品编码
        client:           GrsAIClient 实例
        r2_prefix:        R2 公共访问前缀
        output_dir:       本地输出目录
        target_face_url:  img_2 — 目标模特脸部参考图 URL
        shot_suffixes:    原始拍摄图后缀列表，如 ["_1"] 或 ["_1", "_5"]
        model:            AI 模型名称
        aspect_ratio:     图片比例
        image_size:       图片分辨率（建议 2K）
        negative_prompt:  负向提示词
        background_url:   背景参考图 URL（可选）

    Returns:
        成功保存的本地文件路径列表（失败的跳过不计入）
    """
    shot_suffixes   = shot_suffixes   or FACESWAP_DEFAULT_SHOT_SUFFIXES
    model           = model           or FACESWAP_MODEL
    aspect_ratio    = aspect_ratio    or FACESWAP_ASPECT_RATIO
    image_size      = image_size      or FACESWAP_IMAGE_SIZE
    negative_prompt = negative_prompt or FACESWAP_NEGATIVE_PROMPT

    shot_urls = build_shot_urls(code, r2_prefix, shot_suffixes)
    prompt = build_faceswap_prompt(has_bg_ref=bool(background_url))

    saved_paths: list[str] = []
    os.makedirs(output_dir, exist_ok=True)

    for idx, shot_url in enumerate(shot_urls, start=1):
        suffix = (shot_suffixes or FACESWAP_DEFAULT_SHOT_SUFFIXES)[idx - 1]
        label = f"{code}{suffix}"

        # 槽位：img_1=原片, img_2=脸, img_3=背景(可选)
        urls = [shot_url, target_face_url]
        if background_url:
            urls.append(background_url)

        print(f"\n{'='*60}")
        print(f"[{label}] 开始换脸生成 (shot {idx}/{len(shot_urls)})")
        print(f"  img_1 (原片底图): {shot_url}")
        print(f"  img_2 (目标脸部): {target_face_url}")
        if background_url:
            print(f"  img_3 (背景参考): {background_url}")

        result_url = client.generate_and_wait(
            urls=urls,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            negative_prompt=negative_prompt,
        )

        if not result_url:
            print(f"[{label}] 生成失败，跳过。")
            continue

        out_path = os.path.join(output_dir, f"{label}_faceswap.jpg")
        img_data = requests.get(result_url, timeout=60).content
        with open(out_path, "wb") as f:
            f.write(img_data)
        print(f"[{label}] 已保存 → {out_path}")
        saved_paths.append(out_path)

    return saved_paths


