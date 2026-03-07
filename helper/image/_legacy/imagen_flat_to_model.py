"""
imagen_flat_to_model.py
────────────────────────────────────────────────────────────────────
使用 Google Cloud Vertex AI Imagen 3 将服装平铺图批量生成模特上身效果图。

依赖安装:
    pip install google-cloud-aiplatform

GCP 鉴权 (选其一):
    方案A - 服务账号密钥文件:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/key.json"
    方案B - ADC (本地开发推荐):
        gcloud auth application-default login
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 鉴权：填入服务账号 JSON 路径，或留空使用 ADC ──────────────────────────
SERVICE_ACCOUNT_KEY = ""   # e.g. r"D:\gcp\my-project-key.json"

# ── GCP 项目配置 ───────────────────────────────────────────────────────────
GCP_PROJECT_ID = "your-gcp-project-id"       # TODO: 替换为你的 GCP 项目 ID
GCP_LOCATION   = "us-central1"               # Imagen 3 当前支持的区域
MODEL_ID       = "imagen-3.0-capability-001" # 支持 edit_image 的 Imagen 3 模型

# ── 输入 / 输出目录 ────────────────────────────────────────────────────────
INPUT_DIR  = r"D:\TB\Products\ecco\flat_images"   # TODO: 平铺图所在文件夹
OUTPUT_DIR = r"D:\TB\Products\ecco\model_images"  # 生成结果文件夹（自动创建）

# ── 可选：参考图路径（不需要则留 None）────────────────────────────────────
REFERENCE_FACE_PATH  = None   # e.g. r"D:\TB\ref\model_face.jpg"
REFERENCE_BADGE_PATH = None   # e.g. r"D:\TB\ref\badge_detail.jpg"

# ── 生成参数 ───────────────────────────────────────────────────────────────
PROMPT = (
    "A professional fashion model wearing this exact garment, "
    "studio lighting, clean white minimalist background, "
    "4K high resolution, full body shot, fashion photography style, "
    "all original garment details preserved including buttons and badges"
)
NEGATIVE_PROMPT  = "blurry, low quality, distorted clothes, missing details"
GUIDANCE_SCALE   = 65    # 0-100，越高越贴近原图细节
NUMBER_OF_IMAGES = 1     # 每张输入生成几张结果
MAX_WORKERS      = 2     # 并发线程数（注意 API 配额）
RETRY_COUNT      = 3     # 失败重试次数
RETRY_DELAY_SEC  = 5     # 重试等待秒数

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ──────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _init_vertex() -> None:
    """初始化 Vertex AI SDK，配置鉴权。"""
    if SERVICE_ACCOUNT_KEY:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_KEY

    import vertexai
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)


def _load_model():
    """加载 Imagen 3 编辑模型。"""
    from vertexai.preview.vision_models import ImageGenerationModel
    return ImageGenerationModel.from_pretrained(MODEL_ID)


def _load_vertex_image(path: str):
    """从本地文件加载 Vertex AI Image 对象。"""
    from vertexai.preview.vision_models import Image as VertexImage
    return VertexImage.load_from_file(path)


def _build_edit_kwargs(base_image) -> dict:
    """
    构建 edit_image 调用参数。
    - 使用 mask_mode='background' 自动识别背景并替换
    - 如果有参考图，加入 subject_reference_images
    """
    kwargs: dict = {
        "prompt": PROMPT,
        "base_image": base_image,
        "mask_mode": "background",         # 自动遮罩背景，保护前景（服装）
        "edit_mode": "inpainting-insert",  # 在遮罩区域重新生成内容
        "guidance_scale": GUIDANCE_SCALE,
        "number_of_images": NUMBER_OF_IMAGES,
    }

    if NEGATIVE_PROMPT:
        kwargs["negative_prompt"] = NEGATIVE_PROMPT

    # 参考图（Imagen 3 subject reference，需 SDK >= 1.62）
    reference_images = []
    if REFERENCE_FACE_PATH:
        ref_face = _load_vertex_image(REFERENCE_FACE_PATH)
        reference_images.append({
            "image": ref_face,
            "reference_type": "REFERENCE_TYPE_SUBJECT",
        })
    if REFERENCE_BADGE_PATH:
        ref_badge = _load_vertex_image(REFERENCE_BADGE_PATH)
        reference_images.append({
            "image": ref_badge,
            "reference_type": "REFERENCE_TYPE_STYLE",
        })
    if reference_images:
        kwargs["reference_images"] = reference_images

    return kwargs


def process_single_image(
    model,
    input_path: Path,
    output_dir: Path,
) -> bool:
    """
    处理单张平铺图，生成模特图并保存到 output_dir。
    返回 True 表示成功。
    """
    stem = input_path.stem
    base_image = _load_vertex_image(str(input_path))
    kwargs = _build_edit_kwargs(base_image)

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            log.info("  生成中: %s (第%d次)", input_path.name, attempt)
            response = model.edit_image(**kwargs)

            for idx, result_image in enumerate(response):
                suffix = f"_{idx + 1}" if NUMBER_OF_IMAGES > 1 else ""
                out_path = output_dir / f"{stem}_model{suffix}.jpg"
                result_image.save(str(out_path))
                log.info("  已保存: %s", out_path.name)

            return True

        except Exception as exc:
            log.warning("  失败 [%s] 第%d/%d次: %s", input_path.name, attempt, RETRY_COUNT, exc)
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY_SEC)

    log.error("  跳过 [%s]：已达最大重试次数", input_path.name)
    return False


def batch_process_flat_to_model(
    input_dir: str | Path = INPUT_DIR,
    output_dir: str | Path = OUTPUT_DIR,
    max_workers: int = MAX_WORKERS,
) -> None:
    """
    批量将 input_dir 中的平铺图转换为模特图，结果保存到 output_dir。
    output_dir 不存在时自动创建。
    """
    input_dir  = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("输出目录: %s", output_dir)

    # 收集待处理图片
    image_files = [
        f for f in sorted(input_dir.iterdir())
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not image_files:
        log.warning("未在 %s 中找到支持格式的图片 (%s)", input_dir, SUPPORTED_EXTENSIONS)
        return

    log.info("共找到 %d 张图片，开始批量处理 (并发=%d)…", len(image_files), max_workers)

    _init_vertex()
    model = _load_model()

    success_count = 0
    fail_count    = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_single_image, model, img_path, output_dir): img_path
            for img_path in image_files
        }
        total = len(futures)
        for done_idx, future in enumerate(as_completed(futures), start=1):
            img_path = futures[future]
            try:
                ok = future.result()
            except Exception as exc:
                log.error("意外错误 [%s]: %s", img_path.name, exc)
                ok = False

            if ok:
                success_count += 1
            else:
                fail_count += 1

            log.info("进度: %d/%d  ✓%d  ✗%d", done_idx, total, success_count, fail_count)

    log.info("完成！成功: %d，失败: %d，结果目录: %s", success_count, fail_count, output_dir)


# ── 直接运行入口 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    batch_process_flat_to_model()
