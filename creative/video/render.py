# -*- coding: utf-8 -*-
"""
图片 → 1:1 主图视频。

每张图停留同样时长并缓慢推近/拉远，图与图之间交叉淡化；
字幕按顺序分配到各段图片：短标题 → 卖点1 → 卖点2 → 推荐理由（图片少时从后往前省略）。
编码：H.264 / yuv420p / AAC（静音或背景音乐），+faststart，淘宝可直接上传。
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass
class VideoStyle:
    size: int = 1080                 # 1:1 边长
    fps: int = 30
    duration: float = 15.0           # 总时长（秒）
    max_images: int = 6
    zoom: float = 0.08               # 每段推近/拉远幅度
    fade: float = 0.5                # 图片交叉淡化时长（秒）
    font_path: str = r"C:\Windows\Fonts\msyhbd.ttc"
    font_size: int = 58
    title_font_size: int = 68
    text_color: tuple = (255, 255, 255)
    box_color: tuple = (20, 20, 20, 170)   # 字幕底框 RGBA
    text_bottom: int = 110           # 字幕底框离画面底部的距离（像素）
    crf: int = 20
    music: str | None = None         # 背景音乐文件（mp3/m4a）；None = 静音音轨
    music_start: float = 0.0         # 从音乐第几秒开始
    music_volume: float = 0.8


MUSIC_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}


def list_music(spec: str | Path | None) -> list[Path]:
    """spec 是文件 → [文件]；是文件夹 → 里面全部音乐文件（按文件名排序）；None → []。"""
    if not spec:
        return []
    p = Path(spec)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in MUSIC_EXTS)
        if not files:
            raise FileNotFoundError(f"音乐文件夹里没有音乐文件：{p}")
        return files
    if not p.is_file():
        raise FileNotFoundError(f"找不到背景音乐：{p}")
    return [p]


def media_duration(path: Path) -> float:
    """用 ffmpeg 读时长（秒）；读不到返回 0。"""
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _load_square(path: Path, size: int) -> np.ndarray:
    """读图并放进正方形画布（非正方形用图片四角的平均色补边），返回 RGB uint8。"""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    arr = np.asarray(im)
    corners = np.concatenate([arr[:5, :5], arr[:5, -5:], arr[-5:, :5], arr[-5:, -5:]]).reshape(-1, 3)
    bg = tuple(int(x) for x in corners.mean(axis=0))
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), bg)
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return np.asarray(canvas.resize((size, size), Image.LANCZOS))


def _caption(text: str, style: VideoStyle, title: bool) -> tuple[np.ndarray, np.ndarray] | None:
    """字幕层：返回 (RGB, alpha 0~1)，尺寸同画面。"""
    if not text:
        return None
    s = style.size
    font = ImageFont.truetype(style.font_path, style.title_font_size if title else style.font_size)
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    tw, th = x1 - x0, y1 - y0
    pad_x, pad_y = 44, 26
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    bx, by = (s - bw) // 2, s - style.text_bottom - bh
    draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=bh // 2, fill=style.box_color)
    draw.text((bx + pad_x - x0, by + pad_y - y0), text, font=font, fill=style.text_color)
    arr = np.asarray(layer).astype(np.float32)
    return arr[..., :3], arr[..., 3:] / 255.0


def _zoom(img: np.ndarray, scale: float) -> np.ndarray:
    s = img.shape[0]
    m = cv2.getRotationMatrix2D((s / 2, s / 2), 0, scale)
    return cv2.warpAffine(img, m, (s, s), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def assign_captions(texts: list[str], n_images: int) -> list[str]:
    """把字幕按顺序平均分到 n 张图上（字幕比图多时保留靠前的）。"""
    texts = [t for t in texts if t][:n_images]
    if not texts:
        return [""] * n_images
    return [texts[i * len(texts) // n_images] for i in range(n_images)]


def render_video(images: list[Path], texts: list[str], out_path: Path, style: VideoStyle | None = None) -> Path:
    """texts: [短标题, 卖点1, 卖点2, 推荐理由]，第一个按标题字号显示。"""
    style = style or VideoStyle()
    images = images[:style.max_images]
    if not images:
        raise ValueError("没有图片")
    s, fps = style.size, style.fps
    frames_total = int(round(style.duration * fps))
    n = len(images)
    seg = frames_total / n
    fade_f = max(1, int(style.fade * fps))

    pics = [_load_square(p, s).astype(np.float32) for p in images]
    caps_text = assign_captions(texts, n)
    caps = {t: _caption(t, style, title=(t == texts[0])) for t in set(caps_text) if t}

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".part.mp4")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    audio = (["-ss", f"{style.music_start:.2f}", "-stream_loop", "-1", "-i", str(style.music)] if style.music
             else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
    afilter = (["-af", f"volume={style.music_volume},afade=t=in:st=0:d=0.5,"
                       f"afade=t=out:st={max(0, style.duration - 1.5)}:d=1.5"] if style.music else [])
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{s}x{s}", "-r", str(fps), "-i", "-",
           *audio, "-map", "0:v", "-map", "1:a", *afilter,
           "-c:v", "libx264", "-preset", "medium", "-crf", str(style.crf), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-t", f"{style.duration:.2f}", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(frames_total):
            i = min(int(f / seg), n - 1)
            local = (f - i * seg) / seg                      # 本段进度 0~1
            zin = i % 2 == 0                                 # 单数段推近，双数段拉远
            frame = _zoom(pics[i], 1 + style.zoom * (local if zin else 1 - local))
            into_next = (i + 1) * seg - f                    # 距下一段还有几帧
            if i < n - 1 and into_next <= fade_f:            # 交叉淡化到下一张
                a = 1 - into_next / fade_f
                nxt = _zoom(pics[i + 1], 1 + (0 if (i + 1) % 2 == 0 else style.zoom))
                frame = frame * (1 - a) + nxt * a
            cap = caps.get(caps_text[i])
            if cap:
                rgb, alpha = cap
                # 字幕随段落淡入淡出；相邻两段文字相同时保持不闪
                t_in = 1.0 if i > 0 and caps_text[i - 1] == caps_text[i] else min(1.0, (f - i * seg) / (fps * 0.3))
                t_out = 1.0 if i < n - 1 and caps_text[i + 1] == caps_text[i] else min(1.0, into_next / (fps * 0.3))
                k = alpha * max(0.0, min(t_in, t_out))
                frame = frame * (1 - k) + rgb * k
            proc.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg 失败：{err.strip()[-300:]}")
    except Exception:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out_path)
    return out_path
