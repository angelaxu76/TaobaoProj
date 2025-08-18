import os
import shutil
import json
import glob
import subprocess
from pathlib import Path
from datetime import datetime
from config import CLARKS_JINGYA,TAOBAO_STORES,BRAND_CONFIG
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_all_sku_price_excel
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from brands.clarks_Jingya.unified_link_collector import generate_product_links
from brands.clarks_Jingya.clarks_jinya_fetch_product_info import clarks_fetch_info
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel


BASE_DIR = CLARKS_JINGYA["BASE"]
PUBLICATION_DIR = BASE_DIR / "publication"
REPUB_DIR = BASE_DIR / "repulibcation"
BACKUP_DIR = BASE_DIR / "backup"




def find_uirobot() -> str:
    """
    在常见安装目录中查找 UiRobot.exe（Assistant/Studio）。
    找到即返回完整路径，找不到抛异常。
    """
    home = Path.home().name
    candidates = []
    # Studio 安装路径（你当前能跑的就是这个路径）
    candidates += [rf"C:\Users\{home}\AppData\Local\Programs\UiPath\Studio\UiRobot.exe"]
    # Assistant 多版本目录
    candidates += glob.glob(rf"C:\Users\{home}\AppData\Local\UiPath\app-*\UiRobot.exe")
    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p)
    raise FileNotFoundError("未找到 UiRobot.exe，请确认已安装 UiPath Assistant/Studio。")

def run_uipath_process(process_name: str, input_args: dict | None = None, timeout_s: int = 3600):
    """
    按流程名调用 Assistant 中的流程。
    - 不传 input_args 时，沿用 Assistant 里保存的参数（推荐做法）
    - 需要临时覆盖参数时，传入 dict，会自动序列化为 JSON

    失败会抛异常；成功返回 stdout 文本。
    """
    uirobot = find_uirobot()
    cmd = [uirobot, "execute", "--process-name", process_name]

    if input_args:
        cmd += ["--input", json.dumps(input_args, ensure_ascii=False)]

    # capture_output=True 以便拿到日志；encoding='utf-8' 保证中文正常
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_s
    )
    print("📤 UiPath STDOUT:\n", completed.stdout)
    print("📥 UiPath STDERR:\n", completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"UiPath 流程执行失败，exit code={completed.returncode}")
    return completed.stdout

def backup_and_clear_dir(dir_path: Path, name: str):
    if not dir_path.exists():
        print(f"⚠️ 目录不存在: {dir_path}，跳过")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / timestamp / name
    shutil.copytree(dir_path, backup_path)
    print(f"📦 已备份: {dir_path} → {backup_path}")
    for item in dir_path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    print(f"🧹 已清空目录: {name}")

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CLARKS_JINGYA)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    generate_product_links("clarks_jingya")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    clarks_fetch_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    import_txt_to_db_supplier("clarks_jingya")  # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    insert_jingyaid_to_db("clarks_jingya")

    print("\n🟡 Step: 6️⃣ 调用 UiPath 更新淘宝库存（使用 Assistant 中已保存的参数）")
    run_uipath_process("鲸芽更新clarks男鞋库存版本20250808V2")
    # 如需临时覆盖 Assistant 里的参数（可选）：
    # run_uipath_process("鲸芽更新clarks男鞋库存版本20250808V2", {"date": "2025-08-18"})

if __name__ == "__main__":
    main()