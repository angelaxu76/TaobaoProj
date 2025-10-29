import shutil
import datetime
from pathlib import Path

def backup_and_clear_txt(txt_dir: Path, backup_root: Path):
    """
    仅备份并清空 TXT 目录下的所有 .txt 文件
    """
    if not txt_dir.exists():
        print(f"⚠️ 路径不存在: {txt_dir}")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"txt_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for file in txt_dir.glob("*.txt"):
        shutil.copy(file, backup_dir / file.name)

    for file in txt_dir.glob("*.txt"):
        file.unlink()

    print(f"📦 已备份 TXT → {backup_dir}")
    print(f"🧹 已清空 TXT 目录: {txt_dir}")

def backup_and_clear_dir(dir_path: Path, backup_root: Path, name: str):
    """
    备份整个文件夹并清空（包括子目录和所有文件）
    """
    if not dir_path.exists():
        print(f"⚠️ 目录不存在: {dir_path}，跳过")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / timestamp / name
    shutil.copytree(dir_path, backup_path)
    print(f"📦 已备份: {dir_path} → {backup_path}")

    for item in dir_path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    print(f"🧹 已清空目录: {name}")

def backup_and_clear_brand_dirs(brand_config: dict):
    """
    备份并清空指定品牌的 publication 和 repulibcation 整个文件夹。
    - publication 整个目录（含 TXT/Excel 等）
    - repulibcation 整个目录（含各店铺图片/Excel）
    """
    BASE = brand_config["BASE"]
    BACKUP_DIR = BASE / "backup"

    publication_dir = BASE / "publication"
    repub_dir = BASE / "repulibcation"

    print(f"\n🧼 清理品牌目录: {BASE.name}")

    # 整体备份并清空 publication
    backup_and_clear_dir(publication_dir, BACKUP_DIR, "publication")

    # 整体备份并清空 repulibcation
    backup_and_clear_dir(repub_dir, BACKUP_DIR, "repulibcation")

