from pathlib import Path

def main():
    txt_dir = Path(r"D:\TB\Products\barbour\publication\outdoorandcountry\TXT")
    txt_files = sorted(txt_dir.glob("*.txt"))

    print(f"📂 读取到的 TXT 文件数量: {len(txt_files)}\n")
    for fpath in txt_files:
        print(f" - {fpath.name}")

if __name__ == "__main__":
    main()
