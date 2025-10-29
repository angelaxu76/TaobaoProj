import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# === 导入品牌配置 ===
sys.path.append(str(Path(__file__).resolve().parents[2]))  # 添加根目录到 import 路径
from config import CAMPER  # 只对 Camper 操作

def extract_unpublished_ids(brand_config: dict):
    document_dir = brand_config["BASE"] / "document"
    output_dir = brand_config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)

    # 获取最新 GEI 文件
    gei_files = sorted(document_dir.glob("GEI*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not gei_files:
        print("❌ 未找到 GEI Excel 文件")
        return

    latest_file = gei_files[0]
    print(f"📄 使用最新文件: {latest_file.name}")

    # 读取并筛选
    df = pd.read_excel(latest_file)
    unpublished_df = df[df["铺货状态"] == "未铺货"]
    if unpublished_df.empty:
        print("⚠️ 没有未铺货的商品")
        return

    # 提取并去重
    ids = unpublished_df["渠道产品id"].dropna().astype(str).drop_duplicates()
    result_df = pd.DataFrame({"渠道产品id": ids})

    # 输出路径
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"unpublished_channel_ids_{timestamp}.xlsx"

    result_df.to_excel(output_file, index=False)
    print(f"✅ 已导出未铺货商品 ID，共 {len(result_df)} 个\n📁 文件保存于: {output_file}")

if __name__ == "__main__":
    extract_unpublished_ids(CAMPER)
