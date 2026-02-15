# -*- coding: utf-8 -*-
"""
按 codes.txt 复制 Barbour 图片
- 从 codes_file 读取编码
- 在 out_dir_src 中找文件名包含该编码的图片
- 复制到 dest_img_dir 目录（存在即覆盖）
- 未找到图片的编码输出到 missing_file
"""

import shutil
from pathlib import Path
import re

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # 支持的图片扩展名

def load_codes(codes_file: Path) -> list[str]:
    """
    支持以下格式：
    - 每行一个编码
    - 逗号/空格分隔的多个编码
    - 自动忽略空行与#注释
    """
    codes = []
    if not codes_file.exists():
        raise FileNotFoundError(f"未找到 codes.txt：{codes_file}")
    for line in codes_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[,\s]+", line)  # 按逗号或空格切分
        for p in parts:
            p = p.strip()
            if p:
                codes.append(p)
    # 去重并保留顺序
    seen, unique = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique

def iter_source_images(src_dir: Path):
    for p in src_dir.iterdir():
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            yield p

def move_image_for_publication(
    codes_file: Path,
    out_dir_src: Path,
    dest_img_dir: Path,
    missing_file: Path
):
    dest_img_dir.mkdir(parents=True, exist_ok=True)

    codes = load_codes(codes_file)
    if not codes:
        print("⚠️ codes.txt 没有有效编码。")
        return

    src_files = list(iter_source_images(out_dir_src))
    if not src_files:
        print(f"⚠️ 来源目录无图片：{out_dir_src}")
        return

    files_lower = [(p, p.name.lower()) for p in src_files]  # 文件名小写列表
    missing, copied_count, matched_map = [], 0, {}

    print(f"🔎 待处理编码 {len(codes)} 个，来源图片 {len(src_files)} 张。")
    for code in codes:
        code_lower = code.lower()
        matched = [p for (p, lname) in files_lower if code_lower in lname]

        if not matched:
            missing.append(code)
            continue

        # 排序：优先 _1/_2/_3，再按文件名
        def sort_key(p: Path):
            m = re.search(r"_(\d{1,3})\b", p.stem)
            num = int(m.group(1)) if m else 9999
            return (num, p.name.lower())

        matched.sort(key=sort_key)
        matched_map[code] = matched

        for src in matched:
            dest = dest_img_dir / src.name
            shutil.copy2(src, dest)
            copied_count += 1

        print(f"✅ {code}: 复制 {len(matched)} 张 -> {dest_img_dir}")

    # 写缺图清单
    if missing:
        missing_file.write_text("\n".join(missing) + "\n", encoding="utf-8")
        print(f"⚠️ 缺图编码 {len(missing)} 个，已写入：{missing_file}")

    print("—— 任务完成 ——")
    print(f"📦 成功复制图片总数：{copied_count}")
    print(f"🧾 有图片的编码：{len(matched_map)} / {len(codes)}")
    if missing:
        print(f"❗ 无图片的编码：{len(missing)} （详见 {missing_file.name}）")

if __name__ == "__main__":
    # 示例：使用 config.BARBOUR 配置
    from config import BARBOUR
    codes_file   = BARBOUR["OUTPUT_DIR"] / "missing_image.txt"
    out_dir_src  = Path(r"D:\TB\Products\barbour\images\images")
    dest_img_dir = BARBOUR["OUTPUT_DIR"] / "images"
    missing_file = BARBOUR["OUTPUT_DIR"] / "missing_image.txt"

    move_image_for_publication(codes_file, out_dir_src, dest_img_dir, missing_file)
