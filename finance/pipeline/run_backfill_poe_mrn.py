"""
run_backfill_poe_mrn.py

一次性工具：扫描 POE_References 目录下所有 poe_SD*.pdf，
重新提取 MRN，更新 export_shipments 中 poe_mrn 为 NULL 的记录。

适用场景：旧版 regex 只匹配 25GB 前缀，导致 2026 年 POE 的 MRN 未入库。
"""

import os
import re
from pathlib import Path
from PyPDF2 import PdfReader
import psycopg2
from config import PGSQL_CONFIG

# ── 配置 ──────────────────────────────────────────────────────────────────
POE_REFERENCES_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References"
DRY_RUN = True   # 改为 False 才会真正写数据库
# ─────────────────────────────────────────────────────────────────────────

PDF_PATT = re.compile(r"(?i)poe[_-]?(sd\d+)\.pdf$")
MRN_PATT = re.compile(r"\b(\d{2}GB[A-Z0-9]{14,})\b")


def extract_mrn_from_pdf(pdf_path: str) -> str | None:
    try:
        text = ""
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            text += page.extract_text() or ""
        m = MRN_PATT.search(text)
        return m.group(1) if m else None
    except Exception as e:
        print(f"  [ERROR] 读取 PDF 失败: {pdf_path} — {e}")
        return None


def collect_pdf_mrn_pairs(root: str) -> list[tuple[str, str]]:
    """扫描所有子目录，返回 [(poe_id, mrn), ...] 列表（mrn 非 None 的）"""
    results = []
    for sub in sorted(os.listdir(root)):
        folder = os.path.join(root, sub)
        if not os.path.isdir(folder):
            continue
        for fn in os.listdir(folder):
            m = PDF_PATT.search(fn)
            if not m:
                continue
            poe_id = m.group(1).upper()
            pdf_path = os.path.join(folder, fn)
            mrn = extract_mrn_from_pdf(pdf_path)
            if mrn:
                results.append((poe_id, mrn))
                print(f"  [PDF] {poe_id} → {mrn}")
            else:
                print(f"  [SKIP] {poe_id}: 未找到 MRN")
    return results


def backfill(pairs: list[tuple[str, str]], dry_run: bool) -> int:
    updated = 0
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            for poe_id, mrn in pairs:
                # 只更新 poe_mrn 为 NULL 的记录，避免覆盖已有正确值
                sql = """
                    UPDATE public.export_shipments
                    SET poe_mrn = %s
                    WHERE poe_id = %s
                      AND (poe_mrn IS NULL OR poe_mrn = '')
                """
                if dry_run:
                    # 查一下实际会影响几行
                    cur.execute(
                        "SELECT COUNT(*) FROM public.export_shipments "
                        "WHERE poe_id = %s AND (poe_mrn IS NULL OR poe_mrn = '')",
                        (poe_id,)
                    )
                    n = cur.fetchone()[0]
                    print(f"  [DRY] {poe_id}: 将更新 {n} 行 → poe_mrn = {mrn}")
                    updated += n
                else:
                    cur.execute(sql, (mrn, poe_id))
                    n = cur.rowcount
                    print(f"  [UPDATE] {poe_id}: 已更新 {n} 行 → poe_mrn = {mrn}")
                    updated += n
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return updated


def main():
    print(f"[扫描] {POE_REFERENCES_DIR}")
    pairs = collect_pdf_mrn_pairs(POE_REFERENCES_DIR)

    print(f"\n[汇总] 找到 {len(pairs)} 个 POE PDF 含有效 MRN")

    if not pairs:
        print("没有可回填的数据，退出。")
        return

    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}开始回填...")
    total = backfill(pairs, DRY_RUN)

    if DRY_RUN:
        print(f"\n[DRY RUN 完成] 预计影响 {total} 行。将 DRY_RUN 改为 False 后重新运行以实际更新。")
    else:
        print(f"\n[完成] 共更新 {total} 行。")


if __name__ == "__main__":
    main()
