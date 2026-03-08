# -*- coding: utf-8 -*-
import re
import sys
from pathlib import Path
import shutil

# 正则：开头 11 位编码 + 中划线 + 任意英文名 + "_" + 序号 + 扩展名
# 例：LQU1201BK11-modern-international-polarquilt-jacket_3.jpg
PATTERN = re.compile(r'^([A-Za-z0-9]{11})-[^-].*?_(\d+)\.(jpg|jpeg|png|webp)$', re.IGNORECASE)

def group_and_rename_images(images_dir: Path, code_len: int = 11, overwrite: bool = True):
    if not images_dir.exists() or not images_dir.is_dir():
        print(f"❌ 目录不存在或不是文件夹：{images_dir}")
        return

    # 收集：code -> [(seq_num:int, file_path:Path, ext:str)]
    bucket = {}
    for p in images_dir.iterdir():
        if not p.is_file():
            continue
        m = PATTERN.match(p.name)
        if not m:
            # 不是形如 CODE-xxx_1.jpg 的文件，跳过
            continue
        code, seq_str, ext = m.group(1), m.group(2), m.group(3).lower()
        if len(code) != code_len:
            # 只处理固定长度的 Barbour 编码（默认 11 位）
            continue
        try:
            seq = int(seq_str)
        except ValueError:
            continue
        bucket.setdefault(code, []).append((seq, p, ext))

    if not bucket:
        print("⚠️ 未匹配到任何符合规则的图片文件。")
        return

    total_moved = 0
    for code, items in bucket.items():
        # 按原本编号排序，然后重排为 1..N
        items.sort(key=lambda x: x[0])
        dest_dir = images_dir / code
        dest_dir.mkdir(parents=True, exist_ok=True)

        for new_idx, (_, src_path, ext) in enumerate(items, start=1):
            # 目标统一命名：<code>_<i>.<ext>，扩展名保留
            dest_name = f"{code}_{new_idx}.{ext}"
            dest_path = dest_dir / dest_name

            # 如果已存在且允许覆盖，先删除
            if dest_path.exists() and overwrite:
                try:
                    dest_path.unlink()
                except Exception as e:
                    print(f"⚠️ 无法删除已存在文件：{dest_path}，错误：{e}")

            try:
                shutil.move(str(src_path), str(dest_path))
                total_moved += 1
                print(f"✅ {src_path.name} → {code}/{dest_name}")
            except Exception as e:
                print(f"❌ 移动失败：{src_path} → {dest_path}，错误：{e}")

    print(f"🎯 完成！共移动并重命名 {total_moved} 张图片。")

def group_by_strip_seq(images_dir: Path, overwrite: bool = True):
    """
    通用分组函数：去掉文件名末尾的 _数字 后剩余部分作为分组键。

    支持格式：
      - CODE_1.webp            → 分组到 CODE/CODE_1.webp
      - CODE_COLOR_1.webp      → 分组到 CODE_COLOR/CODE_COLOR_1.webp
      - CODE_COLOR_2.webp      → 分组到 CODE_COLOR/CODE_COLOR_2.webp

    适用品牌：marksandspencer（以及任何遵循 GROUPKEY_序号.ext 命名的图片目录）
    """
    SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
    SEQ_RE = re.compile(r'^(.+)_(\d+)$')
    images_dir = Path(images_dir)

    if not images_dir.exists() or not images_dir.is_dir():
        print(f"❌ 目录不存在或不是文件夹：{images_dir}")
        return

    # 收集：group_key -> [(seq:int, path, ext)]
    bucket = {}
    for p in images_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in SUPPORTED:
            continue
        m = SEQ_RE.match(p.stem)
        if not m:
            continue
        group_key, seq_str = m.group(1), m.group(2)
        bucket.setdefault(group_key, []).append((int(seq_str), p, p.suffix.lower().lstrip(".")))

    if not bucket:
        print("⚠️ 未匹配到任何符合规则的图片文件。")
        return

    total_moved = 0
    for group_key, items in sorted(bucket.items()):
        items.sort(key=lambda x: x[0])
        dest_dir = images_dir / group_key
        dest_dir.mkdir(parents=True, exist_ok=True)

        for new_idx, (_, src_path, ext) in enumerate(items, start=1):
            dest_name = f"{group_key}_{new_idx}.{ext}"
            dest_path = dest_dir / dest_name
            if dest_path.exists() and overwrite:
                try:
                    dest_path.unlink()
                except Exception as e:
                    print(f"⚠️ 无法删除已存在文件：{dest_path}，错误：{e}")
            try:
                shutil.move(str(src_path), str(dest_path))
                total_moved += 1
            except Exception as e:
                print(f"❌ 移动失败：{src_path} → {dest_path}，错误：{e}")

    print(f"🎯 完成！共分组移动 {total_moved} 张图片，{len(bucket)} 个分组。")


if __name__ == "__main__":
    # 用法：python group_barbour_images.py "D:\path\to\images"
    if len(sys.argv) < 2:
        print("用法：python group_barbour_images.py \"D:\\TB\\Products\\barbour\\publication\\images\"")
        sys.exit(1)
    images_dir = Path(sys.argv[1])
    group_and_rename_images(images_dir, code_len=11, overwrite=True)
