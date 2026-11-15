"""
Barbour 换脸产出图重命名入口。

把 FOLDER 下按商品编码分组的图片统一重命名为 {code}__1、{code}__2 ...
排序优先级直接读取 cfg/brands/barbour.py 里的 IMAGE_RENAME_PRIORITY，
其余图片按文件名字母顺序追加。核心逻辑见 ops/image_rename/rename_by_shot_priority.py。

image_process_and_html.py 现在已经会自动跑这一步，正常流程不需要手动单独执行，
这个脚本留作手动预览（dry_run=True）或单独补跑用。

运行：python brands/barbour/pipeline/run_rename_faceswap_images.py
"""
from ops.image_rename.rename_by_shot_priority import rename_by_shot_priority

FOLDER = r"D:\TB\Products\barbour\repulibcation\linkfox_processed"
DRY_RUN = False  # 先预览确认顺序无误，再改成 False 实际重命名

if __name__ == "__main__":
    rename_by_shot_priority(FOLDER, brand="barbour", dry_run=DRY_RUN)
