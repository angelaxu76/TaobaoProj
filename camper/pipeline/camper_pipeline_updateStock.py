import os
import subprocess
from datetime import datetime

# === 路径配置 ===
project_root = r"D:\Projects\TaobaoProj\camper"
venv_python = r"D:\\Projects\\.venv\\Scripts\\python.exe"

# === 各任务路径 ===
scripts = {
    "backup": os.path.join(project_root, r"core\backup_and_clear_publication.py"),
    "get_links": os.path.join(project_root, r"core\GetProductLink.py"),
    "fetch_txt": os.path.join(project_root, r"core\Fetch_Images_TXT_EAN.py"),
    "update_db": os.path.join(project_root, r"stock\UpdateSizeToDB.py"),
    "export_excel": os.path.join(project_root, r"jingya\extract_product_codes_and_unappointProd_from_excel.py"),
    "generate_batch": os.path.join(project_root, r"jingya\generate_ready_to_publish_batch.py"),
    "expand_to_square": os.path.join(project_root, r"image\ResizeImage.py")
}

# === 调用 UiPath 任务路径 ===
uipath_men = r"D:\\UIPATH\\更新camper男鞋库存.xaml"
uipath_women = r"D:\\UIPATH\\更新camper女鞋库存.xaml"

# === 执行步骤 ===
def run_job():
    print("=== Camper pipeline job started ===")
    for name, path in scripts.items():
        print(f"\n🟡 正在执行: {name}")
        subprocess.run([venv_python, path], check=True)

    print("\n🟢 正在启动 UiPath 更新库存流程...")
    subprocess.run(["UiRobot.exe", "-file", uipath_men])
    subprocess.run(["UiRobot.exe", "-file", uipath_women])

    print("\n✅ 所有流程执行完毕！")

if __name__ == "__main__":
    print(f"\n==== 开始执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
    run_job()
