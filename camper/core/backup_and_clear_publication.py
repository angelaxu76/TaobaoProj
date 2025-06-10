import shutil
import datetime
from pathlib import Path

# === 当前产品路径 ===
PUBLICATION_DIR = Path("D:/TB/Products/camper/publication")
BACKUP_DIR = PUBLICATION_DIR.parent.parent / "backup"

def backup_and_clear_publication():
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
        print("ℹ️ publication 目录不存在，跳过清空")

if __name__ == "__main__":
    backup_and_clear_publication()
