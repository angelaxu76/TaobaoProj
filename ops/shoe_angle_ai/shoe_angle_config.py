# ops/shoe_angle_ai/shoe_angle_config.py
"""鞋子产品图视角旋转/微调 —— 专用配置。

这个功能不是淘宝/鲸芽渠道业务逻辑，所以整体放在 ops/ 下自成一体，
不放进 common/（common/ 只放跨品牌/渠道共用的鲸芽业务逻辑）。

GRSAI_API_KEY / GRSAI_HOST / R2_PUBLIC_PREFIX / IMAGE_EXT 这几个是多个 AI
图片流水线（换脸、VTON、LinkFox）共用的全局配置，仍然留在 cfg/ai_config.py，
从 config.py 统一导入；这里只放这个功能独有的设置。
"""

# ── 生成模型参数 ───────────────────────────────────────────────────────────────
SHOE_ANGLE_MODEL        = "nano-banana-2"
SHOE_ANGLE_ASPECT_RATIO = "1:1"
SHOE_ANGLE_IMAGE_SIZE   = "2K"

# ── 三个角度定义（legacy/run_shoe_angle_gen.py 的批量3角度用法用）──────────────
# label      : 输出文件名后缀（angle_01 / angle_02 / angle_03）
# prompt_hint: 在 prompt 中描述视角偏移方向（嵌入主提示词）
SHOE_ANGLE_VARIANTS = [
    {
        "label":       "angle_01",
        "prompt_hint": (
            "Rotate the shoe's viewpoint approximately 5 degrees to the LEFT "
            "(counter-clockwise horizontal camera shift). "
            "The shoe's inner side and left edge should become slightly more visible."
        ),
    },
    {
        "label":       "angle_02",
        "prompt_hint": (
            "Rotate the shoe's viewpoint approximately 5 degrees to the RIGHT "
            "(clockwise horizontal camera shift). "
            "The shoe's outer side and right edge should become slightly more visible."
        ),
    },
    {
        "label":       "angle_03",
        "prompt_hint": (
            "Apply a slight top-down bird's-eye angle shift of approximately 10 degrees "
            "downward. The camera tilts slightly overhead so the toe box and upper "
            "surface of the shoe become more visible."
        ),
    },
]

# ── 负向提示词 ─────────────────────────────────────────────────────────────────
SHOE_ANGLE_NEGATIVE_PROMPT = (
    # 产品细节保护
    "altered logo, missing logo, changed brand name, blurred label, different shoe, "
    "changed color, different material, missing stitching, altered sole pattern, "
    "missing sole details, different lace color, extra decorations, removed eyelets, "
    "changed heel height, distorted shoe shape, stretched proportions, "
    # 背景
    "gray background, dark background, textured background, shadow on background, "
    "gradient background, off-white background, colored background, "
    "floor visible, surface visible, reflections on floor, "
    # 多元素/重复碎片（img_1=img_2 传同一张图时，模型容易多画出一个失败的
    # "细节特写插图"，表现为悬浮在主图上方的模糊碎片）
    "second image, inset image, thumbnail, zoomed detail crop as separate element, "
    "duplicate shoe fragment, floating fragment, ghost duplicate, blurry duplicate overlay, "
    "collage, split-panel layout, multiple views in one frame, two shoes in one image, "
    "cropped extra shoe piece, double exposure, "
    # 画质
    "lowres, blurry, watermark, text, signature, low quality, artifact, "
    "overexposed, underexposed, bad lighting, plastic look, toy shoe, cartoon shoe."
)

# ── R2 写入凭证（仅本功能用：process_one_sku 需要把本地图临时上传到 R2 才能
#    拿到公开 URL 给 API 用；process_one_code_rotate 不需要，因为图已经在
#    R2 上了）─────────────────────────────────────────────────────────────────
# 请在 R2 控制台创建 API Token（Object:Edit 权限），填入以下占位符
R2_ACCOUNT_ID      = "YOUR_R2_ACCOUNT_ID"          # Cloudflare Account ID
R2_WRITE_KEY_ID    = "YOUR_R2_ACCESS_KEY_ID"        # R2 Access Key ID
R2_WRITE_SECRET    = "YOUR_R2_SECRET_ACCESS_KEY"    # R2 Secret Access Key
R2_BUCKET_NAME     = "YOUR_R2_BUCKET_NAME"          # 存储桶名称
# 上传的临时文件在 R2 中的 key 前缀（不含尾部斜杠）
R2_TEMP_UPLOAD_PREFIX = "tmp_shoe_input"
