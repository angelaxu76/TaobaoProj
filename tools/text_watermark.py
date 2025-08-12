# -*- coding: utf-8 -*-
"""
纯文本水印（不含logo）
- auto-corner：自动找低细节区域放一行文本
- tile       ：稀疏斜纹平铺文本
依赖：pip install pillow numpy
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict
import os, glob, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ===== 工具 =====
def _to_rgba(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    return im.convert("RGBA")

def _load_font(font_path: Optional[str], size_px: int) -> ImageFont.FreeTypeFont:
    # 优先用传入字体；否则尝试常见中文/英文字体；最后退到默认字体
    candidates = [font_path, r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", "arial.ttf"]
    for f in candidates:
        if f and Path(f).exists():
            try:
                return ImageFont.truetype(f, size_px)
            except Exception:
                pass
    return ImageFont.load_default()

def _make_text_stamp(text: str, size_px: int, color, shadow: bool, font_path: Optional[str]) -> Image.Image:
    font = _load_font(font_path, size_px)
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d0 = ImageDraw.Draw(tmp)
    bbox = d0.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(2, size_px // 6)

    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        d.text((pad + 1, pad + 1), text, font=font, fill=(0, 0, 0, 140))
    d.text((pad, pad), text, font=font, fill=(*color, 255))
    return im

def _grayscale_np(im: Image.Image) -> np.ndarray:
    g = np.array(im.convert("L")).astype(np.float32)
    return g

def _gradient_map(gray: np.ndarray) -> np.ndarray:
    dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return np.hypot(dx, dy)

def _pick_least_detailed_region(grad: np.ndarray, box_w: int, box_h: int, margin: int) -> Tuple[int, int]:
    H, W = grad.shape
    x0, y0 = margin, margin
    x1, y1 = max(margin, W - margin - box_w), max(margin, H - margin - box_h)
    if x1 < x0 or y1 < y0:
        return margin, margin

    steps = 10
    xs = np.linspace(x0, x1, steps, dtype=int)
    ys = np.linspace(y0, y1, steps, dtype=int)
    best, best_xy = None, (x0, y0)
    for y in ys:
        for x in xs:
            score = float(grad[y:y + box_h, x:x + box_w].mean())
            if best is None or score < best:
                best, best_xy = score, (x, y)
    return best_xy

def _apply_overlay(base: Image.Image, overlay: Image.Image, opacity: float) -> Image.Image:
    if opacity < 1.0:
        r, g, b, a = overlay.split()
        a = a.point(lambda v: int(v * opacity))
        overlay = Image.merge("RGBA", (r, g, b, a))
    return Image.alpha_composite(base, overlay)

# ===== 角标文本水印 =====
def add_text_corner_watermark(
    img: Image.Image,
    text: str = "WATERMARK",
    scale: float = 0.16,          # 文本视觉尺寸：字号≈短边 * scale * 0.5
    opacity: float = 0.16,        # 整体不透明度（0~1）
    margin_ratio: float = 0.03,   # 边距（相对短边）
    font_path: Optional[str] = None,
    auto_color: bool = True,      # 根据放置区域亮度自动选黑/白
    shadow: bool = True,          # 轻阴影，提升可读性
) -> Image.Image:
    base = _to_rgba(img)
    W, H = base.size
    short = min(W, H)
    margin = int(short * margin_ratio)
    size_px = max(18, int(short * scale * 0.5))

    # 先用白色预排版，得到 stamp 尺寸
    tmp_stamp = _make_text_stamp(text, size_px=size_px, color=(255, 255, 255), shadow=shadow, font_path=font_path)
    sw, sh = tmp_stamp.size

    grad = _gradient_map(_grayscale_np(base))
    x, y = _pick_least_detailed_region(grad, sw, sh, margin)

    # 自动颜色：统计该区域亮度
    color = (255, 255, 255)
    if auto_color:
        local_mean = _grayscale_np(base.crop((x, y, x + sw, y + sh))).mean()
        color = (20, 20, 20) if local_mean > 160 else (255, 255, 255)
        # 亮背景→深色且无需阴影；暗背景→浅色+轻阴影
        if local_mean > 160:
            shadow = False

    stamp = _make_text_stamp(text, size_px=size_px, color=color, shadow=shadow, font_path=font_path)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay.paste(stamp, (x, y), stamp)
    return _apply_overlay(base, overlay, opacity)

# ===== 斜纹平铺文本水印 =====
def add_text_tiled_watermark(
    img: Image.Image,
    text: str = "WATERMARK",
    opacity: float = 0.10,
    angle: float = -28.0,
    spacing_ratio: float = 0.30,  # 文本间距（相对短边）
    font_scale: float = 0.06,     # 字号（相对短边）
    font_path: Optional[str] = None,
) -> Image.Image:
    base = _to_rgba(img)
    W, H = base.size
    short = min(W, H)

    font_size = max(18, int(short * font_scale))
    stamp = _make_text_stamp(text, size_px=font_size, color=(255, 255, 255), shadow=False, font_path=font_path)
    sw, sh = stamp.size

    diag = int(math.hypot(W, H))
    draw_area = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    step = max(sh, int(short * spacing_ratio))

    for y in range(0, diag + step, step):
        for x in range(0, diag + step, step):
            draw_area.alpha_composite(stamp, (x, y))

    rotated = draw_area.rotate(angle, expand=True, resample=Image.BICUBIC)
    cx, cy = rotated.size[0] // 2, rotated.size[1] // 2
    crop = rotated.crop((cx - diag // 2, cy - diag // 2, cx + diag // 2, cy + diag // 2))
    crop = crop.crop(((diag - W) // 2, (diag - H) // 2, (diag + W) // 2, (diag + H) // 2))

    return _apply_overlay(base, crop, opacity)

# ===== 批量/管道入口 =====
def _iter_files(input_dir: Path, patterns: List[str], recursive: bool):
    if not patterns:
        patterns = ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"]
    for pat in patterns:
        yield from (Path(p) for p in glob.glob(str(input_dir / ("**" if recursive else "") / pat), recursive=recursive))

def text_watermark_one(
    src: Path,
    dst_dir: Path,
    mode: str = "auto-corner",
    text: str = "WATERMARK",
    opacity: float = 0.16,
    scale: float = 0.16,
    margin_ratio: float = 0.03,
    angle: float = -28.0,
    spacing_ratio: float = 0.30,
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
                out = add_text_tiled_watermark(im, text=text, opacity=opacity, angle=angle,
                                               spacing_ratio=spacing_ratio, font_path=font_path)
            else:
                out = add_text_corner_watermark(im, text=text, scale=scale, opacity=opacity,
                                                margin_ratio=margin_ratio, font_path=font_path)
            fmt = (im.format or "PNG").upper()
            out = out.convert("RGB") if fmt in ("JPEG", "JPG") else out
            out.save(out_path, format=fmt)
        return True, f"保存：{out_path}"
    except Exception as e:
        return False, f"失败：{src} → {e}"

def text_watermark_batch(
    input_dir: str,
    output_dir: str,
    mode: str = "auto-corner",
    pattern: Optional[str] = None,   # 例如 "*.jpg;*.png"
    recursive: bool = False,
    text: str = "EMINZORA TRADE",
    opacity: float = 0.16,
    scale: float = 0.16,
    margin_ratio: float = 0.03,
    angle: float = -28.0,
    spacing_ratio: float = 0.30,
    font_path: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, object]:
    in_dir, out_dir = Path(input_dir), Path(output_dir)
    if not in_dir.exists():
        return {"total": 0, "ok": 0, "fail": 0, "messages": [f"[错误] 输入目录不存在：{in_dir}"]}

    pats = [p.strip() for p in pattern.split(";")] if pattern else []
    files = list(_iter_files(in_dir, pats, recursive))
    if not files:
        return {"total": 0, "ok": 0, "fail": 0, "messages": ["[提示] 未找到文件"]}

    ok = fail = 0
    msgs: List[str] = []
    for f in files:
        s, m = text_watermark_one(
            f, out_dir, mode=mode, text=text, opacity=opacity, scale=scale,
            margin_ratio=margin_ratio, angle=angle, spacing_ratio=spacing_ratio,
            font_path=font_path, overwrite=overwrite
        )
        msgs.append(m)
        ok += int(s); fail += int(not s)
    return {"total": len(files), "ok": ok, "fail": fail, "messages": msgs}

# ===== 命令行（可选）=====
def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="纯文本图片水印（自动角标 / 稀疏斜纹）")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--mode", choices=["auto-corner", "tile"], default="auto-corner")
    p.add_argument("-p", "--pattern", default=None, help='如 "*.jpg;*.png"')
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("--text", default="EMINZORA TRADE")
    p.add_argument("--opacity", type=float, default=0.16)
    p.add_argument("--scale", type=float, default=0.16)
    p.add_argument("--margin", type=float, default=0.03)
    p.add_argument("--angle", type=float, default=-28.0)
    p.add_argument("--spacing", type=float, default=0.30)
    p.add_argument("--font", default=None)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()

def main():
    args = _parse_args()
    res = text_watermark_batch(
        input_dir=args.input, output_dir=args.output, mode=args.mode,
        pattern=args.pattern, recursive=args.recursive, text=args.text,
        opacity=args.opacity, scale=args.scale, margin_ratio=args.margin,
        angle=args.angle, spacing_ratio=args.spacing, font_path=args.font,
        overwrite=args.overwrite,
    )
    for m in res["messages"]:
        print(m)
    print(f"\n完成：成功 {res['ok']} / 失败 {res['fail']} / 总计 {res['total']}")
    return 0 if res["fail"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
