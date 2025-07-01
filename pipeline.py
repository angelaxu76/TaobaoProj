import argparse
import importlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
# === 设置根路径 ===
PROJECT_ROOT = Path(__file__).resolve().parent
BRANDS_DIR = PROJECT_ROOT / "brands"
sys.path.insert(0, str(BRANDS_DIR))

def run_pipeline_for_brand(brand: str):
    runner_filename = f"{brand}_pipeline_runner"
    runner_path = BRANDS_DIR / brand / f"{runner_filename}.py"

    if not runner_path.exists():
        print(f"❌ 未找到 pipeline 文件: {runner_path}")
        return

    try:
        module_path = f"{brand}.{runner_filename}"
        module = importlib.import_module(module_path)
        if hasattr(module, "main"):
            print(f"🚀 正在执行 {brand} 的 pipeline...")
            module.main()
        else:
            print(f"❌ {module_path} 中未定义 main() 函数")
    except Exception as e:
        print(f"❌ 执行 {brand} pipeline 出错: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", required=True, help="品牌名，例如 clarks/camper/geox")
    args = parser.parse_args()
    run_pipeline_for_brand(args.brand.lower())
