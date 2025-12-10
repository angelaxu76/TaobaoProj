# batch_generate_poe_docs.py
from pathlib import Path
from datetime import date

import psycopg2
from config import PGSQL_CONFIG

from finance.ingest.generate_poe_invoice_v2 import generate_poe_invoice_and_report
from finance.ingest.generate_poe_ees_pdf_v2 import generate_poe_ees_pdf

BASE_OUTPUT = Path(r"D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs")


def get_all_poe_ids():
    """
    从 export_shipments 中取出所有存在记录的 POE_ID。
    如你只想生成“有采购成本”的 POE，可以后续加 WHERE 条件。
    """
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT poe_id
        FROM export_shipments
        ORDER BY poe_id
    """)
    poe_ids = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return poe_ids


def main():
    today_str = date.today().strftime("%Y%m%d")

    poe_ids = get_all_poe_ids()
    print(f"[INFO] 共找到 {len(poe_ids)} 个 POE：")
    for pid in poe_ids:
        print("  -", pid)

    for poe_id in poe_ids:
        # 目录结构：D:\...\06_Export_Proofs\<POE_ID>_<日期>
        out_dir = BASE_OUTPUT / f"{poe_id}_{today_str}"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[RUN] 生成 CI + EES: {poe_id}")
        excel_path, docx_path, pdf_path = generate_poe_invoice_and_report(
            poe_id, str(out_dir)
        )
        generate_poe_ees_pdf(poe_id, str(out_dir))

        print("[DONE] Excel 报表:", excel_path)
        print("[DONE] Invoice DOCX:", docx_path)
        print("[DONE] Invoice PDF :", pdf_path)
        print("[DONE] EES PDF 已生成到：", out_dir)

    print("\n[ALL DONE] 全部 POE 已处理完成。")


if __name__ == "__main__":
    main()
