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
    "front_1": "_flat_1",
    "front_2": "_flat_2",
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
VTON_ASPECT_RATIO = "3:4"
VTON_IMAGE_SIZE   = "1K"

# ── 默认款式/领口模式 ──────────────────────────────────────────────────────────
#   "closed"  — 全闭合：高领、立领、拉链到顶的工装/冲锋衣
#   "relaxed" — 自然微张：翻领、Polo、卫衣
#   "layered" — 叠穿外套：开襟夹克/西装，前片自然敞开
VTON_STYLE_MODE = "relaxed"

# ── 负向提示词 ─────────────────────────────────────────────────────────────────
VTON_NEGATIVE_PROMPT = (
    # 幻觉装饰
    "badge on sleeve, arm patch, shoulder logo, embroidery on arm, arm brand label, "
    "extra pockets, extra zippers, asymmetric details not in reference, "
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
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/menmode_1_1.png"
)

# ── 本地输出目录 ───────────────────────────────────────────────────────────────
VTON_OUTPUT_DIR = r"D:\images\ai_gen\output"
