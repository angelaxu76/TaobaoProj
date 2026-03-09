"""
LinkFox AI换模特-2.0 批量处理流水线。

功能：以原始模特拍摄图为底图（imageUrl），替换为目标模特头部（modelImageUrl），
      服装结构 100% 由 LinkFox 保留（API 内部机制）。

与 faceswap_pipeline.py（GrsAI版）的区别：
  - GrsAI 版：通过 prompt 引导 AI 保留服装，效果依赖 prompt 质量
  - LinkFox 版：专用"AI换模特"接口，服装/身体保留由接口自身保障，无需 prompt

典型调用：
    from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox
    from common.ai.image.linkfox_client import LinkFoxClient

    client = LinkFoxClient(api_key="...")
    saved = process_one_linkfox(
        code="MWX2343BL56",
        client=client,
        r2_prefix="https://...r2.dev/product_front",
        output_dir=r"D:\\ms\\linkfox_output",
        model_image_url="https://...target_face.jpg",
        shot_suffixes=["_front_1"],
    )
"""
import os
import requests
from cfg.ai_config import (
    IMAGE_EXT,
    LINKFOX_DEFAULT_SHOT_SUFFIXES,
)


# ── URL 构建 ───────────────────────────────────────────────────────────────────

def build_shot_urls(
    code: str,
    r2_prefix: str,
    shot_suffixes: list[str] | None = None,
) -> list[str]:
    """根据商品编码构建原始拍摄图 URL 列表。

    Args:
        code:          商品编码，如 "MWX2343BL56"
        r2_prefix:     R2 公共访问前缀（含子目录）
        shot_suffixes: 后缀列表，如 ["_front_1"] 或 ["_front_1", "_front_2"]；
                       None 时使用 cfg 的 LINKFOX_DEFAULT_SHOT_SUFFIXES

    Returns:
        URL 列表，顺序对应 shot_suffixes
    """
    if shot_suffixes is None:
        shot_suffixes = LINKFOX_DEFAULT_SHOT_SUFFIXES
    base = r2_prefix.rstrip("/")
    return [f"{base}/{code}{s}{IMAGE_EXT}" for s in shot_suffixes]


# ── 单款处理 ──────────────────────────────────────────────────────────────────

def process_one_linkfox(
    code: str,
    client,
    r2_prefix: str,
    output_dir: str,
    *,
    model_image_url: str,
    shot_suffixes: list[str] | None = None,
    image_seg_url: str | None = None,
    scene_img_url: str | None = None,
    scene_strength: float | None = None,
    gen_ori_res: bool = False,
    real_model: bool = True,
    output_num: int = 1,
    poll_interval: int = 5,
    max_wait: int = 300,
) -> list[str]:
    """对单款商品执行批量 AI 换模特，每张原图生成一组结果图。

    Args:
        code:             商品编码
        client:           LinkFoxClient 实例
        r2_prefix:        R2 公共访问前缀（含子目录）
        output_dir:       本地输出目录
        model_image_url:  目标模特头部参考图 URL（必须）
        shot_suffixes:    原始拍摄图后缀列表；None 时用 cfg 默认值
        image_seg_url:    原图保留区抠图（可选，提升精度）
        scene_img_url:    场景/背景参考图（可选）
        scene_strength:   场景相似度 [0.0, 1.0]（None 时不传，用接口默认 0.7）
        gen_ori_res:      是否生成原分辨率（默认 False）
        real_model:       是否为真人模特（默认 True）
        output_num:       每张原图生成的输出张数 [1, 4]（默认 1）
        poll_interval:    轮询间隔（秒）
        max_wait:         单张最长等待时间（秒）

    Returns:
        成功保存的本地文件路径列表（失败的跳过不计入）
    """
    shot_suffixes = shot_suffixes or LINKFOX_DEFAULT_SHOT_SUFFIXES
    shot_urls = build_shot_urls(code, r2_prefix, shot_suffixes)
    os.makedirs(output_dir, exist_ok=True)

    saved_paths: list[str] = []

    for idx, shot_url in enumerate(shot_urls, start=1):
        suffix = shot_suffixes[idx - 1]
        label  = f"{code}{suffix}"

        print(f"\n{'=' * 60}")
        print(f"[{label}] LinkFox 换模特 (shot {idx}/{len(shot_urls)})")
        print(f"  原始模特图: {shot_url}")
        print(f"  目标模特图: {model_image_url}")

        # 检查原图是否存在（404 则跳过，避免浪费 API 调用）
        try:
            head = requests.head(shot_url, timeout=10)
            if head.status_code == 404:
                print(f"[{label}] 原图不存在 (404)，跳过。")
                continue
        except requests.RequestException as e:
            print(f"[{label}] 原图检查失败 ({e})，跳过。")
            continue

        result_urls = client.change_model_and_wait(
            image_url=shot_url,
            model_image_url=model_image_url,
            image_seg_url=image_seg_url,
            scene_img_url=scene_img_url,
            scene_strength=scene_strength,
            gen_ori_res=gen_ori_res,
            real_model=real_model,
            output_num=output_num,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

        if not result_urls:
            print(f"[{label}] 生成失败，跳过。")
            continue

        # 多输出时加 _a, _b ... 后缀；单输出则不加
        for out_idx, result_url in enumerate(result_urls):
            name_suffix = f"_{chr(ord('a') + out_idx)}" if len(result_urls) > 1 else ""
            out_filename = f"{label}_faceswap{name_suffix}.jpg"
            out_path = os.path.join(output_dir, out_filename)

            try:
                img_data = requests.get(result_url, timeout=60).content
                with open(out_path, "wb") as f:
                    f.write(img_data)
                print(f"[{label}] 已保存 → {out_path}")
                saved_paths.append(out_path)
            except Exception as e:
                print(f"[{label}] 下载结果图失败 ({result_url}): {e}")

    return saved_paths
