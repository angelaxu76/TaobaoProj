"""
Barbour 换脸产出图重命名入口。

把 FOLDER 下按商品编码分组的图片统一重命名为 {code}__1、{code}__2 ...
排序规则：front_N_faceswap（按 N）在前，其次 PRIORITY_SUFFIXES 列出的后缀
（默认只有 "6"），其余图片按文件名字母顺序追加。核心逻辑见
helper/image/rename_by_shot_priority.py。

运行：python brands/barbour/pipeline/run_rename_faceswap_images.py
"""
from helper.image.rename_by_shot_priority import rename_by_shot_priority

FOLDER = r"D:\TB\Products\barbour\repulibcation\linkfox_processed"
PRIORITY_SUFFIXES = ("6",)
DRY_RUN = False  # 先预览确认顺序无误，再改成 False 实际重命名

if __name__ == "__main__":
    rename_by_shot_priority(FOLDER, priority_suffixes=PRIORITY_SUFFIXES, dry_run=DRY_RUN)
