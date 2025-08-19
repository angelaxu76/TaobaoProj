import os
import shutil
import json
import glob
import time
import subprocess
from pathlib import Path
from datetime import datetime

import psycopg2  # 用于查询数据库

from config import CLARKS_JINGYA, TAOBAO_STORES, BRAND_CONFIG
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db, insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel, export_all_sku_price_excel
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from brands.clarks_Jingya.unified_link_collector import generate_product_links
from brands.clarks_Jingya.clarks_jinya_fetch_product_info import clarks_fetch_info
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel

# ================== 常量配置 ==================
BASE_DIR = CLARKS_JINGYA["BASE"]
PUBLICATION_DIR = BASE_DIR / "publication"
REPUB_DIR = BASE_DIR / "repulibcation"
BACKUP_DIR = BASE_DIR / "backup"

# 男款 / 女款参数
GENDER_RUNS = [
    {
        "gender": "男款",
        "success_file": Path(r"D:\clarks_men_success.txt"),
        "uipath_process": "鲸芽更新clarks男鞋库存202508V109",
    },
    {
        "gender": "女款",
        "success_file": Path(r"D:\clarks_women_success.txt"),
        "uipath_process": "鲸芽更新clarks女鞋库存202508V108",
    },
]

DB_CFG = CLARKS_JINGYA["PGSQL_CONFIG"]
TABLE_NAME = CLARKS_JINGYA["TABLE_NAME"]

PENDING_THRESHOLD = 5        # 容忍未更新上限
MAX_RERUNS = 5               # 最多额外循环次数
RERUN_WAIT_SECONDS = 30      # 每次循环之间等待秒数
UIPATH_TIMEOUT = 10800

# ================== 工具函数 ==================
def _safe_decode(b: bytes) -> str:
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
                       timeout_s: int = UIPATH_TIMEOUT) -> str:
    uirobot = find_uirobot()
    cmd = [uirobot, "execute", "--process-name", process_name]
    if input_args:
        cmd += ["--input", json.dumps(input_args, ensure_ascii=False)]

    completed = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    stdout_txt = _safe_decode(completed.stdout or b"")
    stderr_txt = _safe_decode(completed.stderr or b"")

    print("📤 UiPath STDOUT:\n", stdout_txt)
    print("📥 UiPath STDERR:\n", stderr_txt)

    if completed.returncode != 0:
        hints = [
            "① 确认 Assistant 登录了当前 Windows 用户，并能看到该流程；",
            "② 流程名需与 Assistant 完全一致；",
            "③ 首次可先安装：UiRobot.exe installprocess --process-name \"流程名\"；",
            "④ 注意管理员 / 普通用户不一致导致流程列表不同；",
            "⑤ 先在命令行手动验证同命令返回 0。",
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


# ================== 成功文件 & DB 统计 ==================
def reset_success_file(success_path: Path):
    success_path.parent.mkdir(parents=True, exist_ok=True)
    with open(success_path, "w", encoding="utf-8") as f:
        f.write("")
    print(f"🧾 已重置成功记录文件: {success_path}")


def read_success_codes(success_path: Path) -> set[str]:
    if not success_path.exists():
        return set()
    codes = set()
    with open(success_path, "r", encoding="utf-8") as f:
        for line in f:
            code = line.strip()
            if code:
                codes.add(code)
    return codes


def count_distinct_needed_codes(db_cfg: dict, table_name: str, gender: str) -> int:
    sql = f"""
        SELECT COUNT(DISTINCT product_code)
        FROM {table_name}
        WHERE channel_item_id IS NOT NULL
          AND gender = %s
    """
    with psycopg2.connect(**db_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (gender,))
            (cnt,) = cur.fetchone()
            return int(cnt or 0)


def show_pending_status(gender: str, success_file: Path):
    total = count_distinct_needed_codes(DB_CFG, TABLE_NAME, gender=gender)
    done = len(read_success_codes(success_file))
    pending = max(total - done, 0)
    print(f"📊 [{gender}] 需更新(去重)编码={total}，已成功={done}，剩余={pending}")
    return total, done, pending


def run_until_threshold(gender: str, process_name: str, success_file: Path):
    """
    跑指定性别的 UiPath 流程，直到剩余编码 ≤ 阈值或达到最大重试次数。
    """
    # 每个性别单独清空成功文件
    reset_success_file(success_file)

    # 第一次执行
    print(f"\n🟡 Step: 调用 UiPath 更新 {gender} 库存 → {process_name}")
    run_uipath_process(process_name, {"successfulLog": str(success_file)})

    # 循环判断
    total, done, pending = show_pending_status(gender, success_file)

    rerun_count = 0
    while pending > PENDING_THRESHOLD and rerun_count < MAX_RERUNS:
        rerun_count += 1
        print(f"\n🔁 [{gender}] 第 {rerun_count}/{MAX_RERUNS} 次追加执行（剩余 {pending} > {PENDING_THRESHOLD}）...")
        run_uipath_process(process_name, {"successfulLog": str(success_file)})

        if RERUN_WAIT_SECONDS > 0:
            print(f"⏳ 等待 {RERUN_WAIT_SECONDS}s 写入成功日志...")
            time.sleep(RERUN_WAIT_SECONDS)

        total, done, pending = show_pending_status(gender, success_file)

    if pending > PENDING_THRESHOLD:
        print(f"\n⚠️ [{gender}] 达到最大重试（{MAX_RERUNS}），仍有 {pending} 个编码未更新。")
    else:
        print(f"\n✅ [{gender}] 完成：剩余 {pending} ≤ {PENDING_THRESHOLD}。")


# ================== 主流程 ==================
def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CLARKS_JINGYA)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    generate_product_links("clarks_jingya")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    clarks_fetch_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库（库存<2 置 0）")
    import_txt_to_db_supplier("clarks_jingya")

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（导入鲸芽 Excel）")
    insert_jingyaid_to_db("clarks_jingya")

    # 🟡 Step: 6️⃣ 依次更新男款、女款
    for cfg in GENDER_RUNS:
        gender = cfg["gender"]
        success_file = cfg["success_file"]
        process_name = cfg["uipath_process"]
        run_until_threshold(gender, process_name, success_file)


if __name__ == "__main__":
    main()
