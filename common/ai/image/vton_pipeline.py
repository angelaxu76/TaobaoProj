"""
虚拟试穿（Virtual Try-on）流水线辅助模块。

提供：
  - build_image_urls()  — 按商品编码 + R2前缀构建图片 URL 字典
  - build_prompt()      — 构建 nano-banana-2 兼容的生成提示词
  - process_one()       — 单款：提交生成 → 下载 → 保存到本地目录

URL 命名模式（url_mode 参数）：
  "A" — 带独立纹理图的款式（后缀见 cfg/ai_config.py URL_MODE_A_SUFFIXES）
  "B" — 双角度平铺，无独立细节图（后缀见 cfg/ai_config.py URL_MODE_B_SUFFIXES）
"""
import os
import requests
from cfg.ai_config import URL_MODE_A_SUFFIXES, URL_MODE_B_SUFFIXES, IMAGE_EXT


# ── URL 构建 ───────────────────────────────────────────────────────────────────

def build_image_urls(code: str, r2_prefix: str, url_mode: str = "A") -> dict[str, str]:
    """根据商品编码和 R2 前缀生成图片 URL 字典。

    Args:
        code:       商品编码，如 "MWX2343BL56"
        r2_prefix:  R2 公共访问前缀，如 "https://pub-xxx.r2.dev"
        url_mode:   "A" 或 "B"，见模块文档

    Returns:
        key → URL 字典（全部 .jpg，back 在模式 A/B 均包含）
    """
    base = r2_prefix.rstrip("/")
    if url_mode == "A":
        s = URL_MODE_A_SUFFIXES
        return {
            "flat":   f"{base}/{code}{s['flat']}{IMAGE_EXT}",
            "back":   f"{base}/{code}{s['back']}{IMAGE_EXT}",
            "detail": f"{base}/{code}{s['detail']}{IMAGE_EXT}",
        }
    elif url_mode == "B":
        s = URL_MODE_B_SUFFIXES
        return {
            "front_1": f"{base}/{code}{s['front_1']}{IMAGE_EXT}",
            "front_2": f"{base}/{code}{s['front_2']}{IMAGE_EXT}",
            "back":    f"{base}/{code}{s['back']}{IMAGE_EXT}",
        }
    else:
        raise ValueError(f"不支持的 url_mode: {url_mode!r}，请选择 'A' 或 'B'。")


# ── Prompt 构建 ───────────────────────────────────────────────────────────────

def build_prompt(
    garment_src: str,
    detail_src: str,
    bg_clause: str,
    mode: str = "closed",
) -> str:
    """构建 nano-banana-2 兼容的生成提示词。

    Args:
        garment_src:  衣物结构 img 引用，如 "img_2" 或 "img_2 (front) and img_3 (back)"
        detail_src:   纹理细节 img 引用，如 "img_3" 或 "img_4"
        bg_clause:    背景句尾，如 "." 或 " similar to img_5."
        mode:         领口/闭合模式 — "closed" | "relaxed" | "layered"
    """
    if mode == "relaxed":
        neck_instr = (
            f"3. Neckline & Closure: NATURAL OPEN — replicate the EXACT collar opening angle "
            f"and zipper depth as shown in {garment_src}. "
            "Allow the collar to fold or stand naturally following the garment's cut. "
            "If the collar is partially open, show a simple white inner shirt at the opening. "
            "Do NOT force the collar closed or alter its original drape angle. "
        )
    elif mode == "layered":
        neck_instr = (
            f"3. Neckline & Layering: OPEN FRONT — the outer garment is worn open/unbuttoned "
            f"exactly as shown in {garment_src}. "
            "The lapels and front panels must follow the natural drape of the reference. "
            "Show a simple white inner shirt underneath; do NOT close the front opening. "
        )
    else:  # closed（默认）
        neck_instr = (
            f"3. Neckline & Closure: FULLY CLOSED — MANDATORY to replicate the fully closed "
            f"zipper/collar state from {garment_src} with zero opening. "
            "The collar must fit snugly around the model's neck exactly as shown. "
            "Do NOT open the collar or lower the zipper. "
        )

    task_def = (
        "TASK: Professional e-commerce virtual try-on. "
        "INPUT IMAGES — img_1: the target human model (face identity + body pose); "
        f"{garment_src}: flat garment photo (clothing to be worn, structure reference); "
        f"{detail_src}: fabric texture / stitching / logo closeup. "
        "OUTPUT: a photorealistic e-commerce fashion photo of the person from img_1 "
        f"wearing the garment from {garment_src}, textures taken from {detail_src}. "
    )
    return (
        task_def
        + "1. Identity & Face: STRICTLY and ONLY use the facial identity, skin tone, "
        "and head from img_1. "
        "ABSOLUTELY IGNORE any human features, faces, or bodies present in other reference images. "
        "The model in the output MUST be the person from img_1. "
        f"2. Strict Replication: Reconstruct the garment from {garment_src} with ZERO added details. "
        + neck_instr
        + "4. Anti-Hallucination: ABSOLUTELY PROHIBITED to add any logos, badges, patches, "
        "or decorative seams on sleeves, chest, or shoulders unless they are clearly present "
        f"in {garment_src}. "
        f"If a surface is smooth and plain in {garment_src}, "
        "it MUST be rendered as smooth and plain in the output. "
        "5. Layout Fidelity: Maintain the exact non-uniform spacing of buttons, zippers, "
        f"and pocket positions from {garment_src}. Do NOT auto-align or normalize. "
        f"6. Texture: Replicate material luster and stitching from {detail_src} "
        "with pixel-level accuracy. "
        f"7. Background: Professional studio setting{bg_clause} "
        "Output: Ultra-realistic, 8K resolution, e-commerce standard."
    )


# ── 单款处理 ──────────────────────────────────────────────────────────────────

def process_one(
    code: str,
    client,
    r2_prefix: str,
    output_dir: str,
    *,
    model_url: str,
    url_mode: str = "A",
    style_mode: str = "closed",
    model: str = "nano-banana-2",
    aspect_ratio: str = "3:4",
    image_size: str = "1K",
    negative_prompt: str | None = None,
    background_url: str | None = None,
    skip_back: bool = False,
) -> str | None:
    """生成单款商品的虚拟试穿图片并保存到本地。

    Args:
        code:            商品编码
        client:          GrsAIClient 实例
        r2_prefix:       R2 公共访问前缀
        output_dir:      本地输出目录
        model_url:       img_1 — 目标人物模特图 URL
        url_mode:        图片命名模式 "A" 或 "B"
        style_mode:      领口/闭合模式 "closed" | "relaxed" | "layered"
        model:           AI 模型名称
        aspect_ratio:    图片比例
        image_size:      图片分辨率
        negative_prompt: 负向提示词（可选）
        background_url:  背景参考图 URL（可选）
        skip_back:       True 时强制跳过 back 图（即使文件存在）

    Returns:
        保存成功时返回本地文件路径，失败返回 None。
    """
    urls_map = build_image_urls(code, r2_prefix, url_mode)

    # 按 img_n 顺序组装 URL 列表
    urls: list[str] = [model_url]  # img_1 固定为目标模特

    if url_mode == "A":
        urls.append(urls_map["flat"])                      # img_2: 正面平铺
        if urls_map.get("back") and not skip_back:
            urls.append(urls_map["back"])                  # img_3: 背面平铺
            urls.append(urls_map["detail"])                # img_4: 纹理细节
            garment_src = "img_2 (front flat) and img_3 (back flat)"
            detail_src  = "img_4"
            next_idx    = 5
        else:
            urls.append(urls_map["detail"])                # img_3: 纹理细节
            garment_src = "img_2"
            detail_src  = "img_3"
            next_idx    = 4
    else:  # url_mode == "B"
        urls.append(urls_map["front_1"])                   # img_2: 正面角度1
        urls.append(urls_map["front_2"])                   # img_3: 正面角度2
        urls.append(urls_map["back"])                      # img_4: 背面平铺
        garment_src = "img_2 (front angle 1) and img_3 (front angle 2)"
        detail_src  = "img_2"
        next_idx    = 5

    bg_clause = f" similar to img_{next_idx}." if background_url else "."
    if background_url:
        urls.append(background_url)

    prompt = build_prompt(garment_src, detail_src, bg_clause, mode=style_mode)

    print(f"\n{'='*60}")
    print(f"[{code}] 开始生成 (url_mode={url_mode}, style={style_mode})")
    for i, u in enumerate(urls, 1):
        print(f"  img_{i}: {u}")

    result_url = client.generate_and_wait(
        urls=urls,
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        negative_prompt=negative_prompt,
    )

    if not result_url:
        print(f"[{code}] 生成失败。")
        return None

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{code}_generate.jpg")
    img_data = requests.get(result_url, timeout=60).content
    with open(out_path, "wb") as f:
        f.write(img_data)
    print(f"[{code}] 已保存 → {out_path}")
    return out_path
