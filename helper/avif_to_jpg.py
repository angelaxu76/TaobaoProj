from pathlib import Path
from PIL import Image
import pillow_avif  # 启用 AVIF 支持

input_dir = Path(r"D:\TEMP1\image")   # AVIF 文件目录
output_dir = Path(r"D:\TEMP1\image")   # 输出 JPG 目录
output_dir.mkdir(parents=True, exist_ok=True)

for avif_file in input_dir.glob("*.avif"):
    img = Image.open(avif_file)
    out_path = output_dir / (avif_file.stem + ".jpg")
    img.convert("RGB").save(out_path, "JPEG", quality=95)
    print(f"已转换：{avif_file} → {out_path}")
