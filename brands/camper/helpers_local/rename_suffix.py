"""
把 {编码}_{F/C/L/P/T}.jpg 命名的文件改成 {编码}_{1..5}.jpg。

映射固定为 F->1, C->2, L->3, P->4, T->5（按业务要求的顺序，不是字母序）。
只用于 IMAGE_CUTTER（供上传 R2 / AI 视角旋转用），不影响 IMAGE_PROCESS
（HTML 生成读取封面图仍然按 F/C/L/T 字母后缀 + IMAGE_DES_PRIORITY 配置查找，
两个目录互不影响）。
"""
import os

SUFFIX_ORDER = ["F", "C", "L", "P", "T"]
_SUFFIX_TO_NUMBER = {s: i for i, s in enumerate(SUFFIX_ORDER, start=1)}


def rename_letter_suffix_to_numbered(folder) -> None:
    folder = str(folder)

    for filename in os.listdir(folder):
        stem, ext = os.path.splitext(filename)
        if "_" not in stem:
            continue
        code, suffix = stem.rsplit("_", 1)
        number = _SUFFIX_TO_NUMBER.get(suffix.upper())
        if number is None:
            continue  # 已经是数字后缀，或者不认识的后缀，跳过

        src = os.path.join(folder, filename)
        dst = os.path.join(folder, f"{code}_{number}{ext}")
        if os.path.exists(dst):
            print(f"⚠️ 目标文件已存在，跳过改名: {dst}")
            continue
        os.rename(src, dst)
        print(f"✅ 改名: {filename} -> {code}_{number}{ext}")

    print("🚀 编号后缀改名完成！")
