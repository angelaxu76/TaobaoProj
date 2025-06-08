import shutil
import datetime
from pathlib import Path

# === 修改为你当前品牌的路径 ===
PUBLICATION_DIR = Path("D:/TB/Products/camper/publication")
BACKUP_DIR = PUBLICATION_DIR.parent.parent / "backup"

def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{timestamp}/publication"
    print("\n🟡 Step 1：备份并清空整个 publication 目录")

    if PUBLICATION_DIR.exists():
        shutil.copytree(PUBLICATION_DIR, backup_path)
        print(f"📦 已备份: {PUBLICATION_DIR} → {backup_path}")

        for item in PUBLICATION_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        print(f"🧹 已清空: {PUBLICATION_DIR}")
    else:
        PUBLICATION_DIR.mkdir(parents=True)
        print("📁 已新建 publication 目录")
