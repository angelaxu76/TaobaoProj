
from PIL import Image
import os

# 设置图片所在目录
img_dir = r"C:\Users\martin\Desktop\学历\1"   # 修改为你的文件夹路径
# 按文件名排序，确保顺序正确
files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

# 打开图片并统一转为RGB
images = [Image.open(os.path.join(img_dir, f)).convert('RGB') for f in files]

# 第一个作为首页，后面的是追加
output_path = os.path.join(img_dir, "merged.pdf")
images[0].save(output_path, save_all=True, append_images=images[1:])

print(f"✅ 已生成 PDF: {output_path}")
