"""
把 {编码}_{视角}.jpg 命名的文件改成 {编码}_1.jpg ~ {编码}_6.jpg。

GEOX 下载下来的视角后缀是 2 位数字（00/10/30/40/50/60，见
download_product_images.py 里从 URL 解析出的 "_([0-9]{2})\\.jpg"），映射顺序读
ops/image_rename/image_priority_config.py 里 geox 的 IMAGE_CUTTER_RENAME_ORDER（默认
0->1, 10->2, 30->3, 50->4, 60->5, 40->6，按业务要求的顺序，不是数值大小序）。

只用于 IMAGE_CUTTER（供上传 R2 / AI 视角旋转用，这批文件要求严格是
{code}_1.jpg ~ _6.jpg 固定 6 槽位 + 单下划线命名）。IMAGE_PROCESS 目录改名走的是
另一套机制（rename_by_shot_priority + IMAGE_RENAME_PRIORITY，产出双下划线的
{code}__N，按实际存在的文件数量紧凑编号），两者用途不同、字段也分开，不要混用。

映射表里的 key 按整数值比较（"00"和"0"都算 0），改名之后的后缀是 1..6，
不在映射表里，所以重复运行是安全的，不会被二次改名。
"""
import os
from config import GEOX

SUFFIX_ORDER = GEOX["IMAGE_CUTTER_RENAME_ORDER"]
_VALUE_TO_NUMBER = {v: i for i, v in enumerate(SUFFIX_ORDER, start=1)}


def rename_view_suffix_to_numbered(folder) -> None:
    folder = str(folder)

    for filename in os.listdir(folder):
        stem, ext = os.path.splitext(filename)
        if "_" not in stem:
            continue
        code, suffix = stem.rsplit("_", 1)
        if not suffix.isdigit():
            continue
        number = _VALUE_TO_NUMBER.get(int(suffix))
        if number is None:
            continue  # 不在映射表里的后缀（比如已经改过名的 1..6，或未知视角），跳过

        src = os.path.join(folder, filename)
        dst = os.path.join(folder, f"{code}_{number}{ext}")
        if os.path.exists(dst):
            print(f"⚠️ 目标文件已存在，跳过改名: {dst}")
            continue
        os.rename(src, dst)
        print(f"✅ 改名: {filename} -> {code}_{number}{ext}")

    print("🚀 编号后缀改名完成！")
