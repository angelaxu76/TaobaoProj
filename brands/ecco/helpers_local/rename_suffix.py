"""
把 {编码}_{视角}.ext（视角如 o/m/b/s/top_left_pair/front_pair）命名的文件，
按编码分组改名成 {编码}_1.ext / {编码}_2.ext ...

ECCO 每款商品的图片数量、视角名都不固定，不像 Clarks 统一是 _1.._5，而
AI 视角旋转（image_pipeline_step2_ai_rotate.py）和上传 R2
（image_pipeline_step2_upload_to_r2.py）都要求固定编号后缀，所以在 step1
（image_pipeline_step1_download_and_cut.py）末尾统一改名一次。
"""
import os
import re
from collections import defaultdict

_NUMBERED_SUFFIX_RE = re.compile(r"^\d+$")


def rename_views_to_numbered_suffix(folder) -> None:
    """扫描 folder，把每个编码下的图片按视角名排序后改成 _1/_2/... 的编号后缀。

    已经是纯数字后缀的文件（说明改过名了）会跳过，避免重复运行时改错。
    """
    folder = str(folder)
    groups = defaultdict(list)

    for filename in os.listdir(folder):
        stem, ext = os.path.splitext(filename)
        if "_" not in stem:
            continue
        code, suffix = stem.split("_", 1)
        if _NUMBERED_SUFFIX_RE.match(suffix):
            continue
        groups[code].append((suffix, filename, ext))

    for code, items in groups.items():
        items.sort(key=lambda x: x[0])
        for i, (_suffix, filename, ext) in enumerate(items, start=1):
            src = os.path.join(folder, filename)
            dst = os.path.join(folder, f"{code}_{i}{ext}")
            if os.path.exists(dst):
                print(f"⚠️ 目标文件已存在，跳过改名: {dst}")
                continue
            os.rename(src, dst)
            print(f"✅ 改名: {filename} -> {code}_{i}{ext}")

    print("🚀 编号后缀改名完成！")
