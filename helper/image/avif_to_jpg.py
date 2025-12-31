# -*- coding: utf-8 -*-
"""
AVIF → JPG 格式转换（简化版）

用途：
    可在 pipeline 中直接调用，或命令行执行。
    仅需指定输入目录与输出目录。
"""

import os
from pathlib import Path
from PIL import Image
import pillow_avif  # 启用 AVIF 支持

def avif_to_jpg(input_dir: str, output_dir: str):
    """
    将 input_dir 下所有 .avif 图片转换为 .jpg 并保存至 output_dir
    （不递归，不多线程，不调整质量）

    :param input_dir: 源目录
    :param output_dir: 输出目录
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    avif_files = list(input_path.glob("*.avif"))
    print(f"[INFO] 共发现 {len(avif_files)} 个 AVIF 文件。")

    count = 0
    for file in avif_files:
        try:
            img = Image.open(file)
            rgb = img.convert("RGB")
            dst = output_path / (file.stem + ".jpg")
            rgb.save(dst, "JPEG")
            count += 1
        except Exception as e:
            print(f"[ERR] 转换失败：{file.name}，原因：{e}")

    print(f"[OK] 转换完成，共成功 {count} 张。")


# 命令行入口
if __name__ == "__main__":
    # import sys
    # if len(sys.argv) < 3:
    #     print("用法：python avif_to_jpg.py <输入目录> <输出目录>")
    #     sys.exit(1)
    avif_to_jpg(r"C:\Users\martin\Downloads", r"C:\Users\martin\Downloads")
