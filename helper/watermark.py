# -*- coding: utf-8 -*-
"""
轻量水印脚本（尽量不影响美观）
- auto-corner：自动找画面“低细节”区域放角标（水印logo或文字）
- tile       ：稀疏斜纹文字平铺，低不透明度、间距大
依赖：pip install pillow numpy
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict
import os, glob, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# =============== 工具 ===============
def _to_rgba(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    return im.convert("RGBA")

def _grayscale_np(im: Image.Image) -> np.ndarray:
    """转灰度 numpy，范围0~255"""
    g = np.array(im.convert("L"))
    return g.astype(np.float32)

def _gradient_map(gray: np.ndarray) -> np.ndarray:
    """简易梯度图：数值越大表示细节越多"""
    dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return np.hypot(dx, dy)

def _pick_least_detailed_region(grad: np.ndarray, box_w: int, box_h: int, margin: int) -> Tuple[int, int]:
    H, W = grad.shape
    x0 = margin
    y0 = margin
    x1 = max(margin, W - margin - box_w)
    y1 = max(margin, H - margin - box_h)
    if x1 < x0 or y1 < y0:
        return margin, margin  # 图片太小，退化到左上角

    # 网格搜索（稀疏取样，快且够用）
    steps = 10
    xs = np.linspace(x0, x1, steps, dtype=int)
    ys = np.linspace(y0, y1, steps, dtype=int)
    best = None
    best_xy = (x0, y0)
    for y in ys:
        for x in xs:
            patch = grad[y:y+box_h, x:x+box_w]
            score = float(patch.mean())
            if (best is None) or (score < best):
                best = score
                best_xy = (x, y)
    return best_xy

def _apply_overlay(base: Image.Image, overlay: Image.Image, opacity: float = 1.0) -> Image.Image:
    """以不透明度混合一张 RGBA overlay 到 base（RGBA）"""
    if opacity < 1.0:
        # 缩放 overlay alpha
        r, g, b, a = overlay.split()
        a = a.point(lambda v: int(v * opacity))
        overlay = Image.merge("RGBA", (r, g, b, a))
    return Image.alpha_composite(base, overlay)

# =============== 角标水印 ===============
def _make_text_stamp(text: str, size_px: int, color=(255,255,255), shadow=True, font_path: Optional[str]=None) -> Image.Image:
    if font_path and Path(font_path).exists():
        font = ImageFont.truetype(font_path, size_px)
    else:
        try:
            font = ImageFont.truetype("arial.ttf", size_px)  # 通用备选
        except:
            font = ImageFont.load_default()

    # 计算文本尺寸
    tmp = Image.new("RGBA", (10,10), (0,0,0,0))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0,0), text, font=font)
    w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]

    pad = max(2, size_px // 6)
    im = Image.new("RGBA", (w + pad*2, h + pad*2), (0,0,0,0))
    d = ImageDraw.Draw(im)

    if shadow:
        d.text((pad+1, pad+1), text, font=font, fill=(0,0,0,160))
    d.text((pad, pad), text, font=font, fill=(*color, 255))
    return im

def _prepare_logo_stamp(logo_path: str, target_w: int) -> Image.Image:
    logo = Image.open(logo_path).convert("RGBA")
    w, h = logo.size
    if w > target_w:
        ratio = target_w / w
        logo = logo.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
    return logo

def add_corner_watermark(
    img: Image.Image,
    text: Optional[str] = None,
    logo_path: Optional[str] = None,
    scale: float = 0.18,          # 角标宽度相对图像宽度
    opacity: float = 0.18,        # 角标整体不透明度
    margin_ratio: float = 0.03,   # 边距
    font_path: Optional[str] = None,
) -> Image.Image:
    """自适应角标水印（自动找低细节区域）"""
    base = _to_rgba(img)
    W, H = base.size
    margin = int(min(W,H) * margin_ratio)

    if logo_path:
        # logo 宽按比例缩放
        stamp = _prepare_logo_stamp(logo_path, target_w=int(W * scale))
    else:
        # 文本角标
        size_px = max(20, int(min(W,H) * scale * 0.5))
        stamp = _make_text_stamp(text or "WATERMARK", size_px=size_px, color=(255,255,255), shadow=True, font_path=font_path)

    sw, sh = stamp.size

    # 选择“细节最少”的放置位置
    grad = _gradient_map(_grayscale_np(base))
    x, y = _pick_least_detailed_region(grad, sw, sh, margin)

    # 根据局部亮度自动选择文本颜色（仅文本时）
    if logo_path is None:
        local_gray = _grayscale_np(base.crop((x, y, x+sw, y+sh))).mean()
        # 背景偏暗→用浅色；偏亮→用深色
        if local_gray > 160:
            # 重绘深色文本
            size_px = max(20, int(min(W,H) * scale * 0.5))
            stamp = _make_text_stamp(text or "WATERMARK", size_px=size_px, color=(20,20,20), shadow=False, font_path=font_path)

    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    overlay.paste(stamp, (x, y), stamp)
    return _apply_overlay(base, overlay, opacity)

# =============== 斜纹平铺水印 ===============
def add_tiled_watermark(
    img: Image.Image,
    text: str = "WATERMARK",
    opacity: float = 0.10,       # 越低越“隐形”
    angle: float = -30.0,        # 倾斜角度
    spacing_ratio: float = 0.28, # 文本间距（相对短边）
    font_scale: float = 0.06,    # 字号（相对短边）
    font_path: Optional[str] = None,
) -> Image.Image:
    base = _to_rgba(img)
    W, H = base.size
    short = min(W,H)

    # 构建一张较大的画布，旋转后中心裁剪回原尺寸
    diag = int(math.hypot(W,H))
    canvas = Image.new("RGBA", (diag, diag), (0,0,0,0))

    # 文本 stamp
    font_size = max(18, int(short * font_scale))
    stamp = _make_text_stamp(text, size_px=font_size, color=(255,255,255), shadow=False, font_path=font_path)
    sw, sh = stamp.size

    # 以 spacing_ratio 控制稀疏程度
    step = max(sh, int(short * spacing_ratio))
    draw_area = Image.new("RGBA", (diag, diag), (0,0,0,0))
    for y in range(0, diag + step, step):
        for x in range(0, diag + step, step):
            draw_area.alpha_composite(stamp, (x, y))

    rotated = draw_area.rotate(angle, expand=True, resample=Image.BICUBIC)

    # 中心裁剪为 diag x diag，再裁剪回 W x H
    cx, cy = rotated.size[0]//2, rotated.size[1]//2
    crop = rotated.crop((cx - diag//2, cy - diag//2, cx + diag//2, cy + diag//2))
    crop = crop.crop(((diag - W)//2, (diag - H)//2, (diag + W)//2, (diag + H)//2))

    return _apply_overlay(base, crop, opacity)

# =============== 批量 & CLI ===============
def _iter_files(input_dir: Path, patterns: List[str], recursive: bool):
    if not patterns:
        patterns = ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"]
    for pat in patterns:
        yield from (Path(p) for p in glob.glob(str(input_dir / ("**" if recursive else "") / pat), recursive=recursive))

def watermark_one(
    src: Path,
    dst_dir: Path,
    mode: str = "auto-corner",
    text: Optional[str] = None,
    logo_path: Optional[str] = None,
    opacity: float = 0.18,
    scale: float = 0.18,
    margin_ratio: float = 0.03,
    angle: float = -30.0,
    spacing_ratio: float = 0.28,
    font_path: Optional[str] = None,
    overwrite: bool = False,
) -> Tuple[bool, str]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    out_path = dst_dir / src.name
    if (not overwrite) and out_path.exists():
        return False, f"跳过（已存在）：{out_path}"
    try:
        with Image.open(src) as im:
            if mode == "tile":
                out = add_tiled_watermark(im, text=text or "WATERMARK",
                                          opacity=opacity, angle=angle,
                                          spacing_ratio=spacing_ratio, font_path=font_path)
            else:
                out = add_corner_watermark(im, text=text, logo_path=logo_path,
                                           scale=scale, opacity=opacity, margin_ratio=margin_ratio, font_path=font_path)
            # 保留原格式
            fmt = (im.format or "PNG").upper()
            out = out.convert("RGB") if fmt in ("JPEG","JPG") else out
            out.save(out_path, format=fmt)
        return True, f"保存：{out_path}"
    except Exception as e:
        return False, f"失败：{src} → {e}"

def watermark_batch(
    input_dir: str,
    output_dir: str,
    mode: str = "auto-corner",
    pattern: Optional[str] = None, # 如 "*.jpg;*.png"
    recursive: bool = False,
    text: Optional[str] = None,
    logo_path: Optional[str] = None,
    opacity: float = 0.18,
    scale: float = 0.18,
    margin_ratio: float = 0.03,
    angle: float = -30.0,
    spacing_ratio: float = 0.28,
    font_path: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, object]:
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    if not in_dir.exists():
        return {"total":0,"ok":0,"fail":0,"messages":[f"[错误] 输入目录不存在：{in_dir}"]}

    pats = [p.strip() for p in pattern.split(";")] if pattern else []
    files = list(_iter_files(in_dir, pats, recursive))
    if not files:
        return {"total":0,"ok":0,"fail":0,"messages":["[提示] 未找到文件"]}

    ok, fail = 0, 0
    msgs: List[str] = []
    for f in files:
        s, m = watermark_one(
            f, out_dir, mode=mode, text=text, logo_path=logo_path,
            opacity=opacity, scale=scale, margin_ratio=margin_ratio,
            angle=angle, spacing_ratio=spacing_ratio, font_path=font_path,
            overwrite=overwrite,
        )
        msgs.append(m); ok += int(s); fail += int(not s)
    return {"total": len(files), "ok": ok, "fail": fail, "messages": msgs}

# 命令行入口（可选）
def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="图片加水印（尽量不影响美观）")
    p.add_argument("-i","--input", required=True)
    p.add_argument("-o","--output", required=True)
    p.add_argument("--mode", choices=["auto-corner","tile"], default="auto-corner")
    p.add_argument("-p","--pattern", default=None, help='如 "*.jpg;*.png"')
    p.add_argument("-r","--recursive", action="store_true")
    p.add_argument("--text", default=None)
    p.add_argument("--logo", default=None)
    p.add_argument("--opacity", type=float, default=0.18)
    p.add_argument("--scale", type=float, default=0.18)
    p.add_argument("--margin", type=float, default=0.03)
    p.add_argument("--angle", type=float, default=-30.0)
    p.add_argument("--spacing", type=float, default=0.28)
    p.add_argument("--font", default=None)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()

def main():
    args = _parse_args()
    res = watermark_batch(
        input_dir=args.input, output_dir=args.output, mode=args.mode,
        pattern=args.pattern, recursive=args.recursive, text=args.text,
        logo_path=args.logo, opacity=args.opacity, scale=args.scale,
        margin_ratio=args.margin, angle=args.angle, spacing_ratio=args.spacing,
        font_path=args.font, overwrite=args.overwrite,
    )
    for m in res["messages"]:
        print(m)
    print(f"\n完成：成功 {res['ok']} / 失败 {res['fail']} / 总计 {res['total']}")
    return 0 if res["fail"]==0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
