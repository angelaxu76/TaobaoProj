import shutil
from pathlib import Path

def copy_images_by_code(code: str, src_dir: Path, dst_dir: Path):
    """
    拷贝以 code_1.jpg, code_2.jpg ... 命名的图片到目标目录
    """
    for i in range(1, 10):
        filename = f"{code}_{i}.jpg"
        src = src_dir / filename
        if src.exists():
            shutil.copy(src, dst_dir / filename)
