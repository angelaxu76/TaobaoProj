# -*- coding: utf-8 -*-
"""
generate_anna_notes.py
- 与 batch_import_export_shipments.py 一致的 DB 连接逻辑（config.DB_URL 优先，其次 PGSQL_CONFIG）
- 基于 export_shipments 表按 shipment_id 查询对应 POE
- 生成 Anna 账单备注（逐个 shipment 一条），并打印到控制台；可选写入到文件
"""

import os
import datetime as dt
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ---------------------- logging ----------------------
def _now(): return dt.datetime.now().strftime("%H:%M:%S")
def _info(msg: str): print(f"{_now()} [INFO] {msg}")
def _warn(msg: str): print(f"{_now()} [WARN] {msg}")
def _debug(msg: str): print(f"{_now()} [DEBUG] {msg}")

# ---------------------- DB helpers (与导入脚本保持一致) ----------------------
def _db_url_from_config() -> str:
    # 1) config.DB_URL
    try:
        from config import DB_URL  # type: ignore
        if DB_URL:
            _info(f"[DB] Using DB URL from config: {DB_URL}")
            return DB_URL
    except Exception:
        pass
    # 2) config.PGSQL_CONFIG
    try:
        from config import PGSQL_CONFIG  # type: ignore
        user = PGSQL_CONFIG.get("user")
        password = PGSQL_CONFIG.get("password")
        host = PGSQL_CONFIG.get("host", "localhost")
        port = PGSQL_CONFIG.get("port", 5432)
        database = PGSQL_CONFIG.get("database", PGSQL_CONFIG.get("dbname"))
        if not all([user, password, host, port, database]):
            raise KeyError("Missing keys in PGSQL_CONFIG")
        db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        _info(f"[DB] Using DB URL from config: {db_url}")
        return db_url
    except Exception as e:
        raise RuntimeError("无法从 config 读取数据库连接信息。") from e

def _get_engine() -> Engine:
    url = _db_url_from_config()
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as _:
        _info("[DB] Connection OK")
    return eng

# ---------------------- 查询导出 ----------------------
def fetch_poe_by_shipments(shipment_ids: List[str]) -> pd.DataFrame:
    """
    从 export_shipments 表按 shipment_id 列表查询 POE 信息。
    返回列：shipment_id, poe_id, poe_file（若同一个 shipment 对应多 POE，会多行）
    """
    if not shipment_ids:
        return pd.DataFrame(columns=["shipment_id", "poe_id", "poe_file"])

    eng = _get_engine()
    sql = text("""
        SELECT shipment_id, poe_id, poe_file
        FROM export_shipments
        WHERE shipment_id = ANY(:ids)
          AND COALESCE(NULLIF(shipment_id, ''), NULL) IS NOT NULL
    """)
    with eng.connect() as conn:
        df = pd.read_sql(sql, conn, params={"ids": shipment_ids})

    # 规整
    df["shipment_id"] = df["shipment_id"].astype(str).str.strip()
    df["poe_id"] = df["poe_id"].astype(str).str.strip()
    df["poe_file"] = df["poe_file"].astype(str).str.strip()
    # 去重
    df = df.drop_duplicates(subset=["shipment_id", "poe_id"], keep="first")
    return df

def _safe_list(x) -> List[str]:
    return [i for i in x if i and str(i).strip()]

# ---------------------- PO 号生成（可独立脚本调用） ----------------------
def generate_po_number(
    brand: str,
    order_date: Optional[str] = None,   # "YYYYMMDD" 或 "YYYY-MM-DD"
    order_id: Optional[str] = None,
    company_short: str = "EMINZORA",
) -> str:
    """
    简单稳定 PO 命名：<公司简称>-<BRAND>-<YYYYMMDD>-<ORDERID或SEQ>
    不依赖数据库；确保可被“推理”并复现
    """
    brand = (brand or "").upper()
    if order_date:
        try:
            if "-" in order_date:
                d = dt.datetime.strptime(order_date, "%Y-%m-%d").strftime("%Y%m%d")
            else:
                d = dt.datetime.strptime(order_date, "%Y%m%d").strftime("%Y%m%d")
        except Exception:
            d = dt.datetime.now().strftime("%Y%m%d")
    else:
        d = dt.datetime.now().strftime("%Y%m%d")

    tail = (order_id or "SEQ001").replace(" ", "").replace("/", "-")
    return f"{company_short}-{brand}-{d}-{tail}"

# ---------------------- 生成 Anna 备注 ----------------------
def make_anna_notes(
    supplier: str,
    po_number: str,
    shipment_ids: List[str],
    output_txt: Optional[str] = None,
) -> Tuple[List[str], List[str], Dict[str, List[str]]]:
    """
    逐个 shipment 生成一条备注：
    STOCK PURCHASE - <supplier> - P/O: <po_number> - EXPORTED via POE: <poe_id>

    返回：
    - notes: 所有生成的行（已打印）
    - not_found: 数据库未找到的 shipment_id 列表
    - mapping: {shipment_id: [poe_id1, poe_id2, ...]}
    """
    target_ids = [s.strip() for s in shipment_ids if str(s).strip()]
    if not target_ids:
        _warn("空的 shipment_ids。")
        return [], [], {}

    df = fetch_poe_by_shipments(target_ids)

    # build map
    mp: Dict[str, List[str]] = {sid: [] for sid in target_ids}
    for _, r in df.iterrows():
        sid = str(r["shipment_id"]).strip()
        poe = str(r["poe_id"]).strip()
        if sid:
            mp.setdefault(sid, [])
            if poe and poe not in mp[sid]:
                mp[sid].append(poe)

    # notes
    notes: List[str] = []
    not_found: List[str] = []
    for sid in target_ids:
        poe_ids = mp.get(sid, [])
        if not poe_ids:
            not_found.append(sid)
            line = f"STOCK PURCHASE - {supplier} - P/O: {po_number} - EXPORTED via POE: (未找到) - Shipment: {sid}"
        else:
            # 若一个 shipment 有多 POE，按逗号拼接
            line = f"STOCK PURCHASE - {supplier} - P/O: {po_number} - EXPORTED via POE: {', '.join(poe_ids)} - Shipment: {sid}"
        notes.append(line)

    # 控制台打印（方便直接复制粘贴到 Anna）
    _info("------ Anna Notes (copy-paste) ------")
    _info("--------------------------------------")
    for line in notes:
        print(line)
    _info("--------------------------------------")
    _info("----------- End of Notes ------------")

    # 可选写文件
    if output_txt:
        os.makedirs(os.path.dirname(output_txt), exist_ok=True)
        with open(output_txt, "w", encoding="utf-8") as f:
            for line in notes:
                f.write(line + "\n")
        _info(f"[OK] 已写出: {output_txt}")

    return notes, not_found, mp

def make_anna_notes_with_auto_po(
    supplier: str,
    shipment_ids: List[str],
    brand: str = "CAMPER",
    order_date: Optional[str] = None,
    order_id: Optional[str] = None,
    company_short: str = "EMINZORA",
    output_txt: Optional[str] = None,
) -> Tuple[str, List[str], List[str]]:
    """
    先自动生成 PO，再生成备注。返回 (po_number, notes, not_found)
    """
    po_number = generate_po_number(
        brand=brand,
        order_date=order_date,
        order_id=order_id,
        company_short=company_short,
    )
    notes, not_found, _ = make_anna_notes(
        supplier=supplier,
        po_number=po_number,
        shipment_ids=shipment_ids,
        output_txt=output_txt,
    )

    # === 自动打印 Export Evidence Summary 和 POE 路径 ===
    try:
        invoice_no = f"GB-{company_short}-{order_date.replace('-', '')[-6:]}-1" if order_date else f"GB-{company_short}-{dt.datetime.now():%y%m%d}-1"
        evidence_info = get_evidence_files(invoice_no)
        _info("------ Export Evidence Files ------")
        print(evidence_info)
        _info("-----------------------------------")
    except Exception as e:
        _warn(f"无法获取凭证路径信息: {e}")

    return po_number, notes, not_found



# === 生成凭证文件路径 ===
import os
import psycopg2
from config import PGSQL_CONFIG

def get_evidence_files(invoice_no):
    """
    根据 invoice_no 自动获取 Export Evidence Summary 和所有 POE 文件路径。
    """
    base_dir = r"D:\OneDrive\CrossBorderDocs\06_Export_Proofs"

    # 从数据库查出所有 poe_id
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT poe_id, poe_date
        FROM export_shipments
        WHERE uk_invoice_no = %s
        AND poe_id IS NOT NULL
        ORDER BY poe_id;
    """, (invoice_no,))
    poe_records = cur.fetchall()
    conn.close()

    # 提取日期文件夹，例如 20251031
    date_match = ''.join(filter(str.isdigit, invoice_no))
    date_folder = f"20{date_match[-6:]}" if len(date_match) >= 6 else ""
    summary_path = os.path.join(base_dir, date_folder, f"ExportEvidenceSummary_{invoice_no}.pdf")

    result_lines = []
    if os.path.exists(summary_path):
        result_lines.append(f"Export Evidence Summary: {summary_path}")
    else:
        result_lines.append(f"[MISSING] Summary file not found for {invoice_no}")

    if poe_records:
        result_lines.append("\nProof of Export (POE):")
        for idx, (poe_id, poe_date) in enumerate(poe_records, 1):
            poe_file = os.path.join(base_dir, date_folder, f"POE_{poe_id}.pdf")
            if os.path.exists(poe_file):
                result_lines.append(f"{idx}. {poe_file}")
            else:
                result_lines.append(f"{idx}. [MISSING] POE file not found for {poe_id}")
    else:
        result_lines.append("[MISSING] No POE records found in database.")

    return "\n".join(result_lines)



# ---------------------- 简单 CLI/示例 ----------------------
if __name__ == "__main__":
    # 示例：python generate_anna_notes.py
    demo_supplier = "CAMPER UK"
    demo_shipments = ["78944423228164", "78942967207886"]  # 换成你的实际 shipment 列表
    po, _, missing = make_anna_notes_with_auto_po(
        supplier=demo_supplier,
        shipment_ids=demo_shipments,
        brand="CAMPER",
        order_date=None,       # 或 "2025-10-31"
        order_id="789A",       # 你自己的订单编号/记号
        company_short="EMINZORA",
        output_txt=None,       # 也可写到 "D:/OneDrive/CrossBorderDocs/02_Invoices/Reconciliation/anna_notes.txt"
    )
    if missing:
        _warn(f"未在数据库找到的 shipment_id: {missing}")
