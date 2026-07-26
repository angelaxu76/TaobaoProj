# ops/shoe_angle_ai/shoe_angle_config_v1.py
"""鞋子产品图视角旋转 —— 提示词 v1（修复"2D 拉伸伪装成旋转"问题）。

背景：纯侧面（90度侧拍）鞋款用 shoe_angle_config.py 里的原版提示词
（5 度旋转 + 简单的"露出更多内侧/外侧"描述）时，AI 容易走捷径，直接
用 2D 横向挤压/拉伸画面来应付"旋转"指令，而不是真正重绘 3D 视角
（黑色布鞋因为原图本身带斜角，AI 容易找到 3D 轴心，所以没暴露这个问题；
棕色短靴是纯侧面，问题就暴露出来了）。

v1 相对原版的改动：
  1. 角度从 5 度加大到 10～15 度 —— 5 度对模型来说太模糊，容易被
     忽略或用最小的形变敷衍过去。
  2. 正向提示词显式加入"这必须是真 3D 透视变化，不是 2D 拉伸/挤压"的
     强调，并给出具体的透视规律（近大远小/遮挡关系变化/缝线角度
     重新投影），逼模型真正调用 3D 重绘而不是抄近道。
  3. 负向提示词把"禁止 2D 拉伸/挤压"相关词汇前置并强化，避免它们被
     淹没在长串产品细节保护词汇里、跟"旋转"指令产生隐性冲突。

不改动 shoe_angle_config.py 本身（其他已跑通的品类还在用原版），
本文件只新增一套独立的 v1 变量，跟原版互不影响；用哪套由调用方
（process_one_sku / process_one_code_rotate 的 angle_variants /
negative_prompt 参数）决定，参考 run_shoe_angle_gen_v1.py。

模型参数（MODEL / ASPECT_RATIO / IMAGE_SIZE）和 R2 写入凭证跟 v1/v0
共用同一套，不重复定义，直接从 shoe_angle_config.py 导入。
"""
from ops.shoe_angle_ai.shoe_angle_config import (  # noqa: F401  (re-export，方便 v1 脚本单点导入)
    SHOE_ANGLE_MODEL,
    SHOE_ANGLE_ASPECT_RATIO,
    SHOE_ANGLE_IMAGE_SIZE,
    R2_ACCOUNT_ID, R2_WRITE_KEY_ID, R2_WRITE_SECRET,
    R2_BUCKET_NAME, R2_TEMP_UPLOAD_PREFIX,
)

# ── 三个角度定义 v1（run_shoe_angle_gen_v1.py 的批量3角度用法用）───────────────
SHOE_ANGLE_VARIANTS_V1 = [
    {
        "label":       "angle_01",
        "prompt_hint": (
            "A genuine 3D camera perspective shift. Rotate the camera viewpoint "
            "approximately 10 degrees to the LEFT horizontally around the shoe. "
            "This must change the 3D perspective, NOT stretch or compress the 2D image. "
            "The shoe's front toe box moves slightly further away and appears narrower "
            "due to 3D perspective foreshortening. The stitching angle at the heel must "
            "naturally change its 3D spatial alignment."
        ),
    },
    {
        "label":       "angle_02",
        "prompt_hint": (
            "A genuine 3D camera perspective shift. Rotate the camera viewpoint "
            "approximately 10 degrees to the RIGHT horizontally around the shoe. "
            "This must change the 3D perspective, NOT stretch or compress the 2D image. "
            "The heel section rotates closer to the camera, making the heel tab and back "
            "curve slightly more prominent. The side stitching must re-project its angle "
            "according to the new 3D camera view."
        ),
    },
    {
        "label":       "angle_03",
        "prompt_hint": (
            "A genuine 3D camera perspective shift. Apply a slight top-down camera pitch "
            "angle shift of 15 degrees downward. The camera tilts overhead, revealing more "
            "of the upper surface of the leather and the opening of the boot. The sole line "
            "shows a clear curved 3D perspective, showing depth from front to back."
        ),
    },
]

# ── 单角度旋转 v1（run_shoe_angle_rotate_custom_v1.py / process_one_code_rotate
#    的 prompt_hint_fn 参数用；对应 shoe_angle_rotate.build_rotate_prompt_hint 的
#    v1 替代版本，真正生产环境用的是这一路，不是上面的 SHOE_ANGLE_VARIANTS_V1）
# ──────────────────────────────────────────────────────────────────────────────

def build_rotate_prompt_hint_v1(direction: str, degrees: float) -> str:
    """构建"左转/右转 N 度"单角度旋转的 v1 prompt_hint（真 3D 透视描述）。

    跟原版 build_rotate_prompt_hint 的区别：显式声明这是真 3D 相机视角变化、
    不是 2D 拉伸/压缩，并给出该方向对应的具体 3D 透视/遮挡规律（近大远小、
    缝线角度重新投影），逼模型真正重绘视角而不是走"横向挤压"的捷径。
    背景见 shoe_angle_config_v1.py 顶部说明。
    """
    direction = direction.upper()
    if direction == "LEFT":
        detail = (
            "The shoe's front toe box moves slightly further away and appears "
            "narrower due to 3D perspective foreshortening. The stitching angle "
            "at the heel must naturally change its 3D spatial alignment."
        )
    elif direction == "RIGHT":
        detail = (
            "The heel section rotates closer to the camera, making the heel tab "
            "and back curve slightly more prominent. The side stitching must "
            "re-project its angle according to the new 3D camera view."
        )
    else:
        raise ValueError(f"direction 只支持 LEFT/RIGHT，收到: {direction}")

    return (
        "A genuine 3D camera perspective shift. Rotate the camera viewpoint "
        f"approximately {degrees:g} degrees to the {direction} horizontally around "
        "the shoe. This must change the 3D perspective, NOT stretch or compress "
        f"the 2D image. {detail}"
    )


# ── 负向提示词 v1（前置强化"禁止 2D 拉伸/挤压"）─────────────────────────────────
SHOE_ANGLE_NEGATIVE_PROMPT_V1 = (
    # 2D 平面变形/拉伸禁止 —— 前置，避免被后面产品细节词汇淹没
    "2D scaling, 2D stretching, horizontal squeezing, squashed image, "
    "flattened aspect ratio, stretched proportions, distorted shoe shape, "
    # 产品细节保护
    "altered logo, missing logo, changed brand name, blurred label, different shoe, "
    "changed color, different material, missing stitching, altered sole pattern, "
    "missing sole details, different lace color, extra decorations, removed eyelets, "
    "changed heel height, "
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
