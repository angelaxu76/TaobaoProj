# cfg/ai_config.py
"""AI 图片生成相关配置。

包含所有不常变动的全局参数：API 凭证、R2 域名、图片命名规则、
模型参数、提示词等。运营参数（每次运行才改的）留在 ops 脚本中。
"""

# ── GrsAI API ──────────────────────────────────────────────────────────────────
GRSAI_API_KEY = "sk-cb2fd749b4f749198a491588a87375ed"
GRSAI_HOST    = "https://grsaiapi.com"

# ── Cloudflare R2 ──────────────────────────────────────────────────────────────
R2_PUBLIC_PREFIX = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev"

# ── 图片命名后缀（不含扩展名）─────────────────────────────────────────────────
#
# url_mode "A"：带独立纹理特写图
#   {code}_flat.jpg       主正面平铺
#   {code}_back.jpg       背面平铺（可选）
#   {code}_detail_1.jpg   纹理/细节特写
URL_MODE_A_SUFFIXES = {
    "flat":   "_flat",
    "back":   "_back",
    "detail": "_detail_1",
}

# url_mode "B"：双角度平铺，无独立纹理图
#   {code}_flat_1.jpg     正面角度 1
#   {code}_flat_2.jpg     正面角度 2
#   {code}_back.jpg       背面平铺
URL_MODE_B_SUFFIXES = {
    "front_1": "_front_1",
    "front_2": "_front_2",
    "back":    "_back",
}

# 图片文件扩展名（含点）
IMAGE_EXT = ".jpg"

# ── 生成模型参数 ───────────────────────────────────────────────────────────────
#   nano-banana-2        通用生成（需在 prompt 中显式定义任务）
#   nano-banana-fast     快速通用
#   nano-banana-pro-vt   专用虚拟试穿（Virtual Try-on）
#   nano-banana-pro-cl   专用服装生成
#   nano-banana-pro-vip  VIP 高质量（1K/2K）
VTON_MODEL        = "nano-banana-2"
VTON_ASPECT_RATIO = "1:1"
VTON_IMAGE_SIZE   = "1K"

# ── 默认款式/领口模式 ──────────────────────────────────────────────────────────
#   "closed"  — 全闭合：高领、立领、拉链到顶的工装/冲锋衣
#   "relaxed" — 自然微张：翻领、Polo、卫衣
#   "layered" — 叠穿外套：开襟夹克/西装，前片自然敞开
VTON_STYLE_MODE = "closed"

# ── 负向提示词 ─────────────────────────────────────────────────────────────────
VTON_NEGATIVE_PROMPT = (
    # 幻觉装饰
    "badge on sleeve, arm patch, shoulder logo, embroidery on arm, arm brand label, "
    "extra pockets, extra zippers, "
    # 颜色对称化（最常见的失真来源）
    "symmetrized color design, mirrored color pattern, equal color halves, "
    "color normalization, rebalanced color distribution, color blending across panels, "
    "uniform color on both sides, "
    # 结构细节幻觉
    "asymmetric details not in reference, "
    # 领口内里保护
    "inner labels, pattern on inner lining, extra inner buttons, "
    "fused garment layers, messy neckline, "
    # 扣子/领口变形
    "evenly spaced buttons, symmetrically aligned buttons, modified collar, "
    "distorted neckline, "
    # 画质与人体结构
    "lowres, blurry, bad anatomy, deformed fingers, extra limbs, "
    "watermark, text, signature, low quality, artifact."
)

# ── 默认目标模特图（img_1 固定参考）──────────────────────────────────────────
VTON_TARGET_MODEL_URL = (
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.jpg"
)

# ── 本地输出目录 ───────────────────────────────────────────────────────────────
VTON_OUTPUT_DIR = r"D:\images\ai_gen\output"


# ==============================================================================
# Face Swap 专用配置（身份替换 + 背景替换，服装 100% 保留）
# ==============================================================================

# ── Face Swap 生成模型参数 ─────────────────────────────────────────────────────
# 注：R2_SHOT_SUBDIR / SHOT_SUFFIXES / OUTPUT_DIR 已移至 ops/run_ai_face_swap.py
FACESWAP_DEFAULT_SHOT_SUFFIXES = ["_front_1"]
FACESWAP_MODEL        = "nano-banana-2"
FACESWAP_ASPECT_RATIO = "1:1"
FACESWAP_IMAGE_SIZE   = "2K"    # 2K 保留衣服细节，避免 AI 压缩失真

# ── 目标模特脸部参考图列表（img_2，只取脸/发型/肤色）──────────────────────
# 支持多个 URL：多款商品时按商品顺序轮流分配（code 0→url[0], code 1→url[1]...）
# 只填一个 URL 则所有款式使用同一张脸
FACESWAP_TARGET_FACE_URLS = [
    # "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_2.png",
    # "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_1.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_2.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_3.png",
]

# ── 换脸负向提示词 ─────────────────────────────────────────────────────────────
FACESWAP_FACE_DETAIL_PROMPT = (
    "Apply the facial identity of img_2 to the model in img_1 while preserving the original "
    "camera view and body structure from img_1. "
    # --- 比例控制（最高优先级，防止大头照把头撑大）---
    "CRITICAL: Strictly maintain the exact head-to-shoulder scale and medium-shot perspective of img_1. "
    "The head must be naturally small and proportional to the torso, matching the original body scale. "
    "Adopt the medium-shot camera distance and focal length of img_1. "
    "The facial features must be scaled down to match the distant perspective of the original body. "
    "Properly seat the head within the spatial volume of the original neck area. "
    "Do NOT enlarge or zoom in the face area beyond the original head bounding box in img_1. "
    # --------------------------------------------------
    "MANDATORY: Adjust the head rotation, head tilt, facial perspective, and neck alignment "
    "to perfectly match the original neck and body orientation in img_1. "
    "Enforce strong structural depth between the jawline and the neck using deep, sharp shadows. "
    "Ensure the jawline, neck muscles, chin underside, and collar connection look naturally attached, "
    "not pasted on or floating. "
    "Preserve high-frequency skin details including subtle pores, natural skin texture, and fine lines. "
    "Do NOT over-smooth or airbrush the face. "
    "Maintain strong 3D facial structure with realistic shadows on the cheekbones, jawline, and brow ridge. "
    "Facial lighting and shadow direction must strictly follow the lighting on the garment and body in img_1. "
    "In close-up shots, render crisp iris details and moist eye reflections. "
    "The transition between the skin and the garment collar must be a sharp, clear occlusion boundary. "
    "Emphasize realistic eye reflections and catchlights so the eyes look focused and alive. "
    "Preserve detailed baby hairs and fine hair strands along the hairline with natural shadow transition."
)

FACESWAP_HARDWARE_LOCK_PROMPT = (
    "Hardware and neckline lock is MANDATORY. "
    "The zipper slider, zipper teeth, zipper tape, zipper stop, and the circular ring puller "
    "must remain EXACTLY identical to img_1 in position, size, shape, angle, and visible proportion. "
    "DO NOT lower, raise, slide, resize, shrink, or redraw the zipper or ring puller. "
    "The neckline depth, collar opening, collar edge, and the connection point between the collar and zipper "
    "must be a pixel-perfect match to img_1. "
    "Do not alter any garment hardware, trims, stitching, folds, or structural details near the neck and chest."
)

FACESWAP_WHITE_BG_PROMPT = (
    "ABSOLUTELY DISCARD the original background from img_1. "
    "Replace it with a BLOWN-OUT PURE WHITE BACKGROUND. "
    "The entire background must be 100% clipped white (#FFFFFF) with ZERO digital noise, "
    "ZERO luminance variation, and ZERO visible texture. "
    "Ensure the subject is perfectly isolated from any background texture or environmental color contamination. "
    "Use high-key professional e-commerce studio lighting and include only soft, realistic contact shadows on the floor "
    "so the model does not look like she is floating."
)

FACESWAP_WHITE_BG_REF_URL = (
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/white.jpg"
)
FACESWAP_NEGATIVE_PROMPT = (
    # 服装保护（核心）
    "altered clothing, changed garment texture, missing buttons, modified sleeves, "
    "extra logos, blurred fabric, distorted outfit, changed collar, different garment, "
    "re-generated clothes, altered jacket, modified zipper, changed pocket position, "
    # 颜色/对称幻觉
    "symmetrized color design, mirrored color pattern, color normalization, "
    "uniform color on both sides, color blending across panels, "
    # human face realism
    "plastic skin, porcelain face, airbrushed face, over-smoothed skin, waxy skin, "
    "missing skin texture, flat facial shadows, weak jawline, weak cheekbones, "
    "blurry eyes, empty eyes, lifeless expression, cg-like face, cartoonish face, "
    "smooth forehead, fake hairline, overly clean hairline, "
    "floating head, pasted face, misaligned neck, twisted neck, flat face, blurred jawline, "
    "inconsistent lighting, mismatched face angle, wrong head rotation, wrong head tilt, "
    "bad neck connection, disconnected chin shadow, unnatural collar transition, "
    # hardware and zipper protection
    "lowered zipper, raised zipper, moved zipper slider, resized zipper puller, shrunken metal ring, "
    "altered zipper teeth, altered zipper tape, altered zipper stop, changed neckline depth, "
    "changed collar opening, modified ring puller, distorted zipper hardware, resized zipper ring, "
    "changed chest opening, modified placket, modified neck opening, "
    # background replacement
    "original background, preserved background, gray background, grey background, "
    "off-white background, textured wall, wall shadow, messy environment, room background, "
    "background clutter, dirty backdrop, visible backdrop texture, background color cast, "
    "vignetting, studio backdrop texture, floor shadows on wall, dark corners, "
    "ambient occlusion on background, non-white pixels, shadow casting on backdrop, "
    # 头部比例防御（防止大头照来源导致头部撑大）
    "oversized head, big head, disproportionate head-to-shoulder ratio, "
    "zoomed-in face, large face relative to body, face filling the frame, "
    "distorted body proportions, macro shot perspective, close-up face scale, "
    "head larger than original, face out of proportion, enlarged facial area, "
    # 人体结构
    "bad anatomy, deformed fingers, extra limbs, fused fingers, "
    # 画质
    "lowres, blurry, watermark, text, signature, low quality, artifact."
    # --- 新增：针对近景的防御词 ---
    "blurred jawline, merged chin and neck, flat chin shadow, foggy skin texture, "
    "soft facial edges, out-of-focus eyes, unrealistic facial tilt, "
    "plastic skin, porcelain face, airbrushed skin, missing pores, "
    # ----------------------------
)



