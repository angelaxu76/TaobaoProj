import os
import shutil

# ===== 参数配置 =====
SOURCE_DIR = r"D:\TB\Products\barbour\document\images"  # 原始图片目录
TARGET_DIR = r"D:\TB\Products\barbour\document\images_jacket"  # 目标目录
PREFIXES = ("LCA", "LF", "LGI", "LLI", "LQS", "LSP", "LWB", "LWO", "LWX", "MCA", "MGI", "MOS", "MQS", "MQU", "MSP",
            "MTA", "MLI", "MWB","MWO","MWX")  # 文件名前缀

# 创建目标目录（如果不存在）
os.makedirs(TARGET_DIR, exist_ok=True)

# 遍历源目录
for filename in os.listdir(SOURCE_DIR):
    # 检查是否是文件且以指定前缀开头
    if filename.upper().startswith(PREFIXES):
        src_path = os.path.join(SOURCE_DIR, filename)
        dst_path = os.path.join(TARGET_DIR, filename)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)  # 保留原文件时间戳
            print(f"✅ 已复制: {filename}")

print("🎯 完成！")
