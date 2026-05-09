# batch_generate_poe_docs.py
from pathlib import Path
from datetime import date
import shutil  # 用于复制 HK 目录下的 POE PDF

import psycopg2
from config import PGSQL_CONFIG

from finance.ingest.generate_poe_invoice_v2 import (
    generate_poe_invoice_and_report,
    generate_poe_invoice_and_report_by_folder,
)
from finance.ingest.generate_poe_ees_pdf_v2 import (
    generate_poe_ees_pdf,
    generate_poe_ees_pdf_by_folder,
    fetch_poe_header,
)

# UK 这边 CI + EES 输出目录
BASE_OUTPUT = Path(r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\06_Export_Proofs")

# HK 那边原始 POE 文件根目录
HK_POE_BASE = Path(r"C:\Users\angel\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References")

# ── 日期范围过滤（按 poe_date）────────────────────────────────────────
# 留空字符串 "" 表示不限制该端，格式 "YYYY-MM-DD"
DATE_FROM = "2025-09-30"
DATE_TO   = "2026-04-02"
# ──────────────────────────────────────────────────────────────────────


def get_null_poe_folders():
    """
    获取日期范围内所有 poe_id 为空的批次，按 folder_name 返回。
    使用 folder_name (YYYYMMDD) 作为日期过滤，因为这类批次的 poe_date 也可能为空。
    """
    conditions = []
    params = []
    if DATE_FROM:
        conditions.append("folder_name >= %s")
        params.append(DATE_FROM.replace("-", ""))
    if DATE_TO:
        conditions.append("folder_name <= %s")
        params.append(DATE_TO.replace("-", ""))

    where_date = ("AND " + " AND ".join(conditions)) if conditions else ""

    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT folder_name
        FROM export_shipments
        WHERE (poe_id IS NULL OR poe_id = '')
          AND folder_name IS NOT NULL AND folder_name != ''
          {where_date}
        ORDER BY folder_name
    """, params)
    folders = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return folders


def get_all_poe_ids():
    """
    从 export_shipments 中取出 POE_ID，可按 poe_date 范围过滤。
    DATE_FROM / DATE_TO 均为空时取全部。
    """
    conditions = []
    params = []
    if DATE_FROM:
        conditions.append("poe_date >= %s")
        params.append(DATE_FROM)
    if DATE_TO:
        conditions.append("poe_date <= %s")
        params.append(DATE_TO)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT poe_id
        FROM export_shipments
        {where}
        ORDER BY poe_id
    """, params)
    poe_ids = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return poe_ids


def copy_poe_pdf_from_hk(poe_id: str, poe_date_str: str, out_dir: Path) -> None:
    """
    尝试从 HK 目录中找到对应的 POE PDF，并复制到 UK 的 out_dir 中。

    HK 目录结构示例：
        D:\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References\
            20251003\POE_SD10009849381617.pdf
            20251022\poe_SD10009905718779.pdf
    我们用如下规则寻找：
        - 子目录名 = poe_date_str (YYYYMMDD)
        - 文件名中包含 poe_id（不区分大小写），扩展名为 .pdf
    """
    src_dir = HK_POE_BASE / poe_date_str
    if not src_dir.exists():
        print(f"[WARN] HK POE 目录不存在：{src_dir}")
        return

    target_lower = poe_id.lower()
    found = None

    for pdf_path in src_dir.glob("*.pdf"):
        if target_lower in pdf_path.name.lower():
            found = pdf_path
            break

    if not found:
        print(f"[WARN] 未在 {src_dir} 中找到包含 {poe_id} 的 POE PDF 文件。")
        return

    # 目标文件名：保持原文件名
    dest_path = out_dir / found.name
    try:
        shutil.copy2(found, dest_path)
        print(f"[OK] 已复制 POE PDF 到 UK 目录: {dest_path}")
    except Exception as e:
        print(f"[ERROR] 复制 POE PDF 失败: {found} -> {dest_path}，原因: {e}")


def main():

    poe_ids = get_all_poe_ids()
    print(f"[INFO] 共找到 {len(poe_ids)} 个 POE：")
    for pid in poe_ids:
        print("  -", pid)

    for poe_id in poe_ids:

        # -------------------------------
        # 获取 POE 日期作为目录名
        # -------------------------------
        header = fetch_poe_header(poe_id)
        poe_date = header.get("poe_date")

        if poe_date is None:
            # 若数据库为空则 fallback，用今天日期（极少情况）
            poe_date_str = date.today().strftime("%Y%m%d")
        else:
            # 确保日期格式化正确
            if hasattr(poe_date, "strftime"):
                poe_date_str = poe_date.strftime("%Y%m%d")
            else:
                # 兜底：字符串形式（避免异常）
                poe_date_str = str(poe_date).replace("-", "")

        # 最终目录格式：
        #   <POE_ID>_<POE_DATE>
        out_dir = BASE_OUTPUT / f"{poe_id}_{poe_date_str}"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[RUN] 生成 CI + EES: {poe_id}")

        # 1) CI：如果该 POE 没有任何采购成本（旧库存/非ANNA采购），则跳过 CI
        excel_path = docx_path = pdf_path = None
        try:
            excel_path, docx_path, pdf_path = generate_poe_invoice_and_report(
                poe_id, str(out_dir)
            )
            print("[OK] CI 已生成")
            print("     Excel:", excel_path)
            print("     DOCX :", docx_path)
            print("     PDF  :", pdf_path)
        except ValueError as e:
            # 你遇到的就是这一类：poe_id 中没有任何填写采购成本的商品 -> 不需要 CI
            print(f"[SKIP] CI 跳过：{e}")

        # 2) EES：无论是否生成 CI，都要生成（用于证明出口事实）
        generate_poe_ees_pdf(poe_id, str(out_dir))


        # -------------------------------
        # 从 HK 目录复制原始 POE PDF
        # -------------------------------
        copy_poe_pdf_from_hk(poe_id, poe_date_str, out_dir)

        # print("[DONE] Excel 报表:", excel_path)
        # print("[DONE] Invoice DOCX:", docx_path)
        # print("[DONE] Invoice PDF :", pdf_path)
        print("[DONE] EES PDF 已生成到：", out_dir)

    # ── 处理无 POE ID 的批次（按 folder_name）──────────────────────────────
    null_folders = get_null_poe_folders()
    if null_folders:
        print(f"\n[INFO] 以下批次无 POE ID，将按 folder_name 仅生成 CI（跳过 EES）：")
        for fn in null_folders:
            print(f"  - {fn}")

        for folder_name in null_folders:
            out_dir = BASE_OUTPUT / f"FOLDER-{folder_name}"
            out_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n[RUN] 生成 CI (no POE ID): folder_name={folder_name}")
            try:
                excel_path, docx_path, pdf_path = generate_poe_invoice_and_report_by_folder(
                    folder_name, str(out_dir)
                )
                print("[OK]  CI 已生成")
                print("      Excel:", excel_path)
                print("      DOCX :", docx_path)
                print("      PDF  :", pdf_path)
            except ValueError as e:
                print(f"[SKIP] CI 跳过：{e}")

            # EES：用 folder_name 作为 POE Reference 生成（做账用）
            try:
                ees_path = generate_poe_ees_pdf_by_folder(folder_name, str(out_dir))
                print(f"[OK]  EES 已生成：{ees_path}")
            except Exception as e:
                print(f"[WARN] EES 跳过：{e}")

            print(f"[DONE] 输出目录：{out_dir}")

    print("\n[ALL DONE] 全部 POE 已处理完成。")


if __name__ == "__main__":
    main()
