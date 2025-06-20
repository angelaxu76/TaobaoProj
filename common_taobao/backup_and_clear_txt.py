import shutil
import datetime
from pathlib import Path

def backup_and_clear_txt(txt_dir: Path, backup_root: Path):
    """
    将 txt_dir 备份到 backup_root 中带时间戳目录，并清空 txt_dir。
    - 不处理 images 等其他目录
    """
    if not txt_dir.exists():
        print(f"⚠️ 路径不存在: {txt_dir}")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"txt_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 拷贝所有 TXT 文件
    for file in txt_dir.glob("*.txt"):
        shutil.copy(file, backup_dir / file.name)

    # 清空原 TXT 目录
    for file in txt_dir.glob("*.txt"):
        file.unlink()

    print(f"📦 已备份 TXT → {backup_dir}")
    print(f"🧹 已清空 TXT 目录: {txt_dir}")