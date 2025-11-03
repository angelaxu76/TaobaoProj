#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline-callable importer with rich debug logs.

Usage (pipeline):
    from import_poe_invoice_debug import import_poe_invoice
    import_poe_invoice(r"D:\OneDrive\CrossBorderDocs\06_Export_Proofs")

CLI:
    python import_poe_invoice_debug.py --root "D:/OneDrive/CrossBorderDocs/06_Export_Proofs" --verbose
"""

import os
import re
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from PyPDF2 import PdfReader
from sqlalchemy import create_engine, text

# ---------------- Logging ----------------
def _setup_logger(verbose: bool):
    lvl = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

log = logging.getLogger(__name__)

# ---------------- Config ----------------
try:
    import config  # 确保 PYTHONPATH 能找到你的 config.py
except Exception as e:
    config = None

def _get_db_url_from_config() -> str:
    if config is None or not hasattr(config, "PGSQL_CONFIG"):
        raise RuntimeError("config.PGSQL_CONFIG 未找到，请在 config.py 中提供数据库配置。")
    pg = config.PGSQL_CONFIG

    if isinstance(pg, dict):
        url = pg.get("SQLALCHEMY_URL") or pg.get("alchemy_url") or pg.get("url")
        if url:
            return url
        host = pg.get("host") or pg.get("HOST")
        port = pg.get("port") or pg.get("PORT") or 5432
        user = pg.get("user") or pg.get("USER")
        password = pg.get("password") or pg.get("PASSWORD")
        database = pg.get("database") or pg.get("dbname") or pg.get("DBNAME")
        if not all([host, user, password, database]):
            raise RuntimeError("PGSQL_CONFIG 缺少 host/user/password/database 字段或 SQLALCHEMY_URL。")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    elif isinstance(pg, str):
        return pg
    else:
        raise RuntimeError("PGSQL_CONFIG 类型不支持，应为 dict 或 连接串。")

# ---------------- Constants ----------------
INVOICE_EXTS = {".xlsx", ".xls"}
POE_EXTS = {".pdf"}

RE_POE_ID = re.compile(r"\b(SD\d{8,})\b")
RE_MRN_LABELED = re.compile(r"MRN[:\s]*([0-9A-Z]{16,18})")
RE_MRN = re.compile(r"\b([0-9A-Z]{16,18})\b")
RE_OFFICE = re.compile(r"\b(GB\d{5,6})\b")
RE_DDMMYYYY = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

TARGET_COLS = [
    "skuid",
    "lp_number",
    "product_description",
    "value_gbp",
    "quantity",
    "net_weight_kg",
    "hs_code",
    "poe_id",
    "hmrc_mrn",
    "poe_filename",
    "export_date",
    "office_of_exit",
    "src_folder",
    "src_invoice_file",
    "src_poe_file",
]

def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").strip().lower())

# 中英双语列名映射（可自行扩充）
COL_KEYS = {
    "skuid": {"skuid","商品idskuid","商品id","sku_id","sku","商品id（skuid）"},
    "lp_number": {"lp订单号lpnumber","lpnumber","lp订单号","lp no","lpno","lp"},
    "product_description": {"产品英文名productdescription","productdescription","产品英文名","product name","product title","title","description"},
    "value_gbp": {"价值（gbp）value(gbp)","value(gbp)","价值（gbp）","valuegbp","value","gbp","amount"},
    "quantity": {"数量quantity","quantity","数量","qty","q'ty"},
    "net_weight_kg": {"净重（kg）netweight(kg)","netweight(kg)","净重（kg）","netweightkg","netweight","weight"},
    "hs_code": {"欧盟税号hscode","hscode","欧盟税号","hs","hs code","hs-code"},
}

# ---------------- Helpers ----------------
def _find_files(folder: Path, exts: set) -> List[Path]:
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]

def _read_invoice_any(inv_path: Path) -> pd.DataFrame:
    try:
        xls = pd.ExcelFile(inv_path)
        df = xls.parse(xls.sheet_names[0])
        log.debug(f"[INVOICE] Loaded via ExcelFile: {inv_path.name} (rows={len(df)})")
        return df
    except Exception as e:
        log.debug(f"[INVOICE] ExcelFile failed, fallback to read_excel(openpyxl): {inv_path.name} ({e})")
        df = pd.read_excel(inv_path, engine="openpyxl")
        log.debug(f"[INVOICE] Loaded via read_excel: {inv_path.name} (rows={len(df)})")
        return df

def _map_invoice_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    raw_cols = list(df.columns)
    norm_cols = [_norm(c) for c in raw_cols]

    use_cols = {}
    for target, candidates in COL_KEYS.items():
        chosen = None
        for i, nc in enumerate(norm_cols):
            if nc in candidates:
                chosen = raw_cols[i]
                break
        if chosen is None:
            for i, nc in enumerate(norm_cols):
                if target in nc:  # contains fallback
                    chosen = raw_cols[i]; break
        if chosen:
            use_cols[target] = chosen

    log.debug(f"[INVOICE] Mapping => {use_cols}")

    # create or assign columns
    for t in ("skuid","lp_number","product_description","value_gbp","quantity","net_weight_kg","hs_code"):
        df[t] = df[use_cols[t]] if t in use_cols else None

    df = df[["skuid","lp_number","product_description","value_gbp","quantity","net_weight_kg","hs_code"]]

    # numeric cleanup
    def _to_num(x):
        try:
            return float(str(x).replace(",", "").strip())
        except Exception:
            return None

    df["value_gbp"] = df["value_gbp"].map(_to_num)
    df["quantity"] = df["quantity"].map(_to_num)
    df["net_weight_kg"] = df["net_weight_kg"].map(_to_num)

    return df

def _normalize_lp_cell(x: str) -> list:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    s = str(x).upper()
    parts = re.split(r"[,\;\|\t\r\n ]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    parts = [p for p in parts if p.startswith("SD")]  # 只保留 SD 开头
    return parts

def _parse_poe(pdf_path: Path) -> dict:
    poe_filename = pdf_path.name
    text_all = ""
    with open(pdf_path, "rb") as f:
        r = PdfReader(f)
        for p in r.pages:
            text_all += p.extract_text() or ""

    m = RE_POE_ID.search(text_all)
    poe_id = m.group(1) if m else (re.search(r"(SD\d+)", poe_filename).group(1) if re.search(r"(SD\d+)", poe_filename) else None)

    m = RE_MRN_LABELED.search(text_all)
    if m:
        mrn = m.group(1)
    else:
        m = RE_MRN.search(text_all)
        mrn = m.group(1) if m else None

    office = None
    m = RE_OFFICE.search(text_all)
    if m:
        office = m.group(1)

    export_date = None
    m = RE_DDMMYYYY.search(text_all)
    if m:
        try:
            export_date = datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
        except Exception:
            export_date = None

    return {
        "poe_id": poe_id,
        "hmrc_mrn": mrn,
        "poe_filename": poe_filename,
        "export_date": export_date,
        "office_of_exit": office,
    }

# ---------------- Core ----------------
def import_poe_invoice(
    root_path: str,
    table: str = "export_shipments",
    schema: Optional[str] = "public",
    verbose: bool = True,
    dry_run: bool = False,
    limit: Optional[int] = None,   # 限制每个子目录最多入库多少行（便于测试）
) -> int:
    """Scan subfolders under root_path, parse all invoices and POEs, match by LP==POE,
    and append matched rows into existing `export_shipments` table. Returns inserted row count."""
    _setup_logger(verbose)

    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Root not found: {root}")

    db_url = _get_db_url_from_config()
    log.info(f"[DB] Using DB URL from config: {db_url}")
    engine = create_engine(db_url)

    # 先试连一次（及早暴露连接问题）
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("[DB] Connection OK")
    except Exception as e:
        log.exception("[DB] Connection failed")
        raise

    total_rows = 0
    subfolders = [p for p in sorted(root.iterdir()) if p.is_dir()]
    log.info(f"[SCAN] Found {len(subfolders)} subfolder(s) under {root}")

    for folder in subfolders:
        inv_files = _find_files(folder, INVOICE_EXTS)
        poe_files = _find_files(folder, POE_EXTS)
        log.info(f"\n[SCAN] Folder: {folder.name} -> {len(inv_files)} invoice(s), {len(poe_files)} POE(s)")

        if not inv_files or not poe_files:
            log.warning(f"[SKIP] Missing invoices or POEs in {folder.name}")
            continue

        # 解析所有 POE
        poe_rows = []
        for pf in poe_files:
            row = _parse_poe(pf)
            row["src_poe_file"] = pf.name
            poe_rows.append(row)
            log.debug(f"[POE] {pf.name} -> poe_id={row.get('poe_id')}, mrn={row.get('hmrc_mrn')}, office={row.get('office_of_exit')}, date={row.get('export_date')}")

        df_poe = pd.DataFrame(poe_rows).dropna(subset=["poe_id"]).drop_duplicates(subset=["poe_id"])
        if df_poe.empty:
            log.warning(f"[WARN] No valid poe_id extracted in {folder.name}. Skip.")
            continue

        poe_index = df_poe.set_index("poe_id")
        log.info(f"[POE] Extracted {len(df_poe)} unique poe_id(s). Sample: {list(df_poe['poe_id'])[:5]}")

        # 解析所有发票并 explode LP
        inv_frames = []
        for inv in inv_files:
            df_raw = _read_invoice_any(inv)
            df_map = _map_invoice_columns(df_raw)
            log.debug(f"[INVOICE] {inv.name} mapped columns: {list(df_map.columns)}")
            before_rows = len(df_map)

            df_map["_lp_list"] = df_map["lp_number"].map(_normalize_lp_cell)
            exploded = df_map.explode("_lp_list", ignore_index=True)
            exploded["lp_norm"] = exploded["_lp_list"].fillna("")
            exploded["src_folder"] = folder.name
            exploded["src_invoice_file"] = inv.name

            log.info(f"[LP] {inv.name}: {before_rows} row(s) -> exploded to {len(exploded)} row(s)")
            # 显示前几个 LP 样本
            sample_lp = exploded["lp_norm"].dropna().unique().tolist()[:5]
            log.debug(f"[LP] sample LPs: {sample_lp}")

            inv_frames.append(exploded)

        df_inv_all = pd.concat(inv_frames, ignore_index=True) if inv_frames else pd.DataFrame()
        if df_inv_all.empty:
            log.warning(f"[WARN] No invoice rows after mapping/explode in {folder.name}")
            continue

        # 主匹配
        matched = df_inv_all.join(poe_index, how="left", on="lp_norm")
        total_folder = len(df_inv_all)
        matched_rows = matched["poe_filename"].notna().sum()
        unmatched_rows = total_folder - matched_rows
        log.info(f"[MATCH] {matched_rows}/{total_folder} matched in folder {folder.name}")

        if unmatched_rows > 0:
            # 简要展示未匹配样本
            sample_unmatched = matched.loc[~matched["poe_filename"].notna(), "lp_norm"].head(10).tolist()
            log.debug(f"[UNMATCHED] sample lp_norm (first 10): {sample_unmatched}")

        matched = matched[matched["poe_filename"].notna()].copy()
        if matched.empty:
            log.warning(f"[WARN] Nothing matched in {folder.name}, skip insert.")
            continue

        # 限流（便于测试）
        if limit and limit > 0 and len(matched) > limit:
            log.info(f"[LIMIT] Take first {limit} row(s) for insertion (from {len(matched)})")
            matched = matched.head(limit)

        # 对应 export_shipments 的列
        for col in TARGET_COLS:
            if col not in matched.columns:
                matched[col] = None

        out = matched[
            ["skuid","lp_number","product_description","value_gbp","quantity","net_weight_kg","hs_code",
             "poe_id","hmrc_mrn","poe_filename","export_date","office_of_exit",
             "src_folder","src_invoice_file","src_poe_file"]
        ].copy()

        # 最后几条插入前样本
        log.debug(f"[DB] Sample rows to insert (tail 5):\n{out.tail(5).to_string(index=False)}")

        if dry_run:
            log.info(f"[DRY-RUN] Would insert {len(out)} row(s) from {folder.name} -> {schema}.{table}")
        else:
            out.to_sql(
                name=table,
                con=engine,
                schema=schema,
                if_exists="append",
                index=False,
                chunksize=500,
                method="multi",
            )
            log.info(f"[DB] Inserted {len(out)} row(s) -> {schema}.{table}")
            total_rows += len(out)

    log.info(f"\n[SUMMARY] Inserted total rows: {total_rows}")
    return total_rows

# ---------------- CLI ----------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Import matched invoice+POE rows into DB (export_shipments) with debug logs")
    ap.add_argument("--root", required=True, help="Root folder containing subfolders like 20251103/")
    ap.add_argument("--table", default="export_shipments", help="Destination table name")
    ap.add_argument("--schema", default="public", help="DB schema")
    ap.add_argument("--verbose", action="store_true", help="Verbose debug logs")
    ap.add_argument("--dry-run", action="store_true", help="Do not write to DB, just simulate")
    ap.add_argument("--limit", type=int, default=0, help="Limit rows per folder for testing")
    args = ap.parse_args()

    import_poe_invoice(
        root_path=args.root,
        table=args.table,
        schema=args.schema,
        verbose=args.verbose,
        dry_run=args.dry_run,
        limit=args.limit if args.limit and args.limit > 0 else None,
    )
