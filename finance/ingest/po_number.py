# -*- coding: utf-8 -*-
"""
finance/ingest/po_number.py

无状态 PO 号生成器：不依赖数据库。规则可预测、稳定、可复现。
格式：
  {COMPANY}-{BRAND}-{YYYYMMDD}-{ORDERNO 或 S{HASH6}}

- 若提供 order_no：直接使用 order_no（清洗为 A-Z0-9-）
- 否则若提供 shipment_ids：使用去重/排序后的 shipment_ids 计算 SHA1，取 6 位 Base36 校验后缀
- 若两者都没有：仅返回 {COMPANY}-{BRAND}-{YYYYMMDD}
"""

from __future__ import annotations
import argparse
import hashlib
import re
from datetime import datetime
from typing import Iterable, Optional, List

ALNUM_DASH = re.compile(r"[^A-Z0-9\-]+")

def _clean_token(s: str) -> str:
    s = (s or "").strip().upper().replace(" ", "-").replace("_", "-")
    s = ALNUM_DASH.sub("", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s

def _date_str(d: Optional[str] = None) -> str:
    """
    支持：None / '2025-10-31' / '20251031'
    """
    if not d:
        return datetime.now().strftime("%Y%m%d")
    d = str(d).strip()
    if re.fullmatch(r"\d{8}", d):
        return d
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%Y%m%d")
    except Exception:
        # 容错：尽量抽取数字
        digits = re.sub(r"[^\d]", "", d)
        return (digits[:8] or datetime.now().strftime("%Y%m%d"))

def _base36(n: int) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if n == 0:
        return "0"
    out = []
    nn = abs(n)
    while nn > 0:
        nn, r = divmod(nn, 36)
        out.append(chars[r])
    return "".join(reversed(out))

def _hash_suffix_from_shipments(shipment_ids: Iterable[str], length: int = 6) -> str:
    uniq_sorted = sorted({(s or "").strip() for s in shipment_ids if str(s).strip()})
    base = "|".join(uniq_sorted)
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()  # 40 hex
    # 取前 10 个 hex -> 转 int -> base36 -> 截取
    n = int(h[:10], 16)
    b36 = _base36(n)
    return b36[:length].upper().rjust(length, "0")

def generate_po(
    company: str,
    brand: str,
    date_str: Optional[str] = None,
    order_no: Optional[str] = None,
    shipment_ids: Optional[Iterable[str]] = None,
    max_len: int = 64,
) -> str:
    """
    生成可预测的 PO 编号。确保幂等（同样输入 -> 同样输出）。
    """
    company_c = _clean_token(company or "COMPANY")
    brand_c = _clean_token(brand or "BRAND")
    date_c = _date_str(date_str)

    tail = ""
    if (order_no or "").strip():
        tail = _clean_token(order_no or "")
    elif shipment_ids:
        suffix = _hash_suffix_from_shipments(shipment_ids, length=6)
        tail = f"S{suffix}"

    parts: List[str] = [p for p in [company_c, brand_c, date_c, tail] if p]
    po = "-".join(parts)

    # 控长度（保留前缀结构）
    if len(po) > max_len:
        # 尽量不截断 company-brand-date
        head = "-".join([company_c, brand_c, date_c])
        remain = max_len - len(head) - 1  # 减去一个 '-'
        if remain <= 0:
            return (head[:max_len]).rstrip("-")
        return f"{head}-{tail[:remain]}".rstrip("-")

    return po


# --- CLI ---
def _cli():
    ap = argparse.ArgumentParser(description="Generate deterministic PO number.")
    ap.add_argument("--company", required=True, help="公司简称，如 EMINZORA")
    ap.add_argument("--brand", required=True, help="品牌，如 CAMPER")
    ap.add_argument("--date", default=None, help="YYYYMMDD 或 YYYY-MM-DD，不传则今天")
    ap.add_argument("--order-no", default=None, help="若提供则直接使用；否则用 shipment_ids 推导")
    ap.add_argument("--shipments", default="", help="逗号分隔的 shipment_id 列表")
    ap.add_argument("--max-len", type=int, default=64, help="最大长度，默认 64")
    args = ap.parse_args()

    shipment_ids = [s.strip() for s in args.shipments.split(",") if s.strip()]
    po = generate_po(
        company=args.company,
        brand=args.brand,
        date_str=args.date,
        order_no=args.order_no,
        shipment_ids=shipment_ids or None,
        max_len=args.max_len,
    )
    print(po)

if __name__ == "__main__":
    _cli()
