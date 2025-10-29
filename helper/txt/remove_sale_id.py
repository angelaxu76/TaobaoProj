import os

# === 配置部分 ===
sale_file = r"C:\Users\martin\Desktop\打折\sale.txt"   # sale.txt 路径（可改）
target_dir = r"C:\Users\martin\Desktop\打折\英国伦敦"           # 目标目录（存放camper.txt等）
# =================

# 读取 sale.txt 中的商品ID
with open(sale_file, "r", encoding="utf-8") as f:
    sale_ids = set(line.strip() for line in f if line.strip())

# 遍历目录下所有 txt 文件
for filename in os.listdir(target_dir):
    if filename.endswith(".txt") and filename != os.path.basename(sale_file):
        filepath = os.path.join(target_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        # 删除 sale.txt 中出现的ID
        filtered = [id_ for id_ in lines if id_ not in sale_ids]

        removed = len(lines) - len(filtered)
        print(f"{filename}：删除了 {removed} 个匹配ID")

        # 重新写回文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(filtered) + "\n")
