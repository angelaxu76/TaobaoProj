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

def _safe_decode(b: bytes) -> str:
    # 先试 UTF-8，再退到系统本地编码，再到 cp936，最后忽略非法字节
    for enc in ("utf-8", "mbcs", "cp936"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", errors="ignore")

def find_uirobot() -> str:
    home = Path.home().name
    candidates = [
        rf"C:\Users\{home}\AppData\Local\Programs\UiPath\Studio\UiRobot.exe",
        *glob.glob(rf"C:\Users\{home}\AppData\Local\UiPath\app-*\UiRobot.exe"),
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p)
    raise FileNotFoundError("未找到 UiRobot.exe，请确认已安装 UiPath Assistant/Studio。")

def run_uipath_process(process_name: str,
                       input_args: dict | None = None,
                       timeout_s: int = 3600) -> str:
    """
    通过流程名调用 Assistant 流程。
    - 不传 input_args：沿用 Assistant 中保存的参数
    - 返回：解码后的 STDOUT 字符串；失败则抛异常并输出可读日志
    """
    uirobot = find_uirobot()
    cmd = [uirobot, "execute", "--process-name", process_name]
    if input_args:
        cmd += ["--input", json.dumps(input_args, ensure_ascii=False)]

    # 用 bytes 捕获，避免编码问题；不设 text/encoding
    completed = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout_s
    )

    stdout_txt = _safe_decode(completed.stdout or b"")
    stderr_txt = _safe_decode(completed.stderr or b"")

    print("📤 UiPath STDOUT:\n", stdout_txt)
    print("📥 UiPath STDERR:\n", stderr_txt)

    if completed.returncode != 0:
        # 给出常见排查点
        hints = [
            "① 确认 Assistant 登录了当前 Windows 用户，并能看到该流程；",
            "② 流程名需与 Assistant 完全一致（中英文和空格都要一致）；",
            "③ 如果是首次在本机运行，可先安装：UiRobot.exe installprocess --process-name \"流程名\"；",
            "④ 如果 Python 以管理员运行，而 Assistant 以普通用户运行，两个用户的流程列表不一致（建议同一用户）；",
            "⑤ 在命令行里手动跑同样命令看是否 0 退出码；",
        ]
        raise RuntimeError(
            f"UiPath 流程执行失败，exit code={completed.returncode}\n"
            f"STDOUT:\n{stdout_txt}\nSTDERR:\n{stderr_txt}\n\n"
            + "📌 排查建议：\n- " + "\n- ".join(hints)
        )
    return stdout_txt


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