# -*- coding: utf-8 -*-
"""
将编码写回 TXT 并重命名为 {product_code}.txt
用法（在 pipeline 中）：
    from barbour.common.fill_codes_into_txt import backfill_product_codes_to_txt
    summary = backfill_product_codes_to_txt("very")  # 只传 supplier 名称
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, Tuple, Optional

import psycopg2

from config import PGSQL_CONFIG, BARBOUR

# Barbour 编码判定：如 MWX0339NY91 / LQU1234BK11 等
RE_CODE = re.compile(r'^[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}$')
NO_CODE_VALUES = {"", "no data", "null", "n/a", "none"}

# 兼容旧键名（极少数 TXT 用 Product Color Code）
PRODUCT_CODE_LINE_PATS = [
    re.compile(r'(?i)^(Product\s+Code)\s*:\s*(.*)$'),
    re.compile(r'(?i)^(Product\s+Color\s+Code)\s*:\s*(.*)$'),
]

def _get_conn():
    return psycopg2.connect(**PGSQL_CONFIG)

def _extract_field(text: str, label_regex: str) -> Optional[str]:
    m = re.search(label_regex, text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    line = m.group(0)
    parts = line.split(":", 1)
    if len(parts) < 2:
        return None
    return parts[1].strip()

def _extract_site_url(txt: str) -> Tuple[str, str]:
    site = _extract_field(txt, r'^Site\s*Name\s*:.*$') or ""
    url  = _extract_field(txt, r'^Source\s*URL\s*:.*$') or ""
    return site.strip(), url.strip()

def _is_code_filename(p: Path) -> bool:
    name = p.stem.upper()
    return bool(RE_CODE.match(name))

def _load_mapping_siteurl_to_code() -> Dict[Tuple[str, str], str]:
    """从 barbour_products 预加载 (site_name.lower(), source_url) -> product_code 映射。"""
    sql = """
      SELECT DISTINCT lower(COALESCE(source_site,'')) AS site_name,
                      COALESCE(source_url,'')         AS source_url,
                      product_code
        FROM barbour_products
       WHERE source_site IS NOT NULL
         AND source_url  IS NOT NULL
         AND product_code IS NOT NULL
    """
    mapping: Dict[Tuple[str, str], str] = {}
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        for site, url, code in cur.fetchall():
            if site and url and code:
                mapping[(site, url)] = code
    return mapping

def _find_product_code_line(lines):
    """返回 (idx, key_label, current_val)；若未找到返回 (None, None, None)"""
    for idx, line in enumerate(lines):
        for pat in PRODUCT_CODE_LINE_PATS:
            m = pat.match(line)
            if m:
                label = m.group(1)  # 原键名
                val = (m.group(2) or "").strip()
                return idx, label, val
    return None, None, None

def _should_overwrite(val: Optional[str]) -> bool:
    return (val is None) or (val.strip().lower() in NO_CODE_VALUES) or (not RE_CODE.match(val.strip().upper()))

def _rename_to_code(fp: Path, code: str) -> Path:
    target = fp.with_name(f"{code}.txt")
    if target.exists() and target.resolve() != fp.resolve():
        i = 2
        while True:
            alt = fp.with_name(f"{code}_{i}.txt")
            if not alt.exists():
                target = alt
                break
            i += 1
    if target.resolve() != fp.resolve():
        fp = fp.rename(target)
    return fp

def backfill_product_codes_to_txt(supplier: str) -> dict:
    """
    入口函数：只传 supplier 名称
    步骤：
      1) 遍历 TXT
      2) 文件名已是编码 → 跳过
      3) 读 Site Name/Source URL → 查 DB 拿 code
      4) 写回 Product Code 行（没有则新增），并把文件重命名为 {code}.txt
    返回：摘要字典，便于 pipeline 打日志
    """
    txt_dirs = BARBOUR.get("TXT_DIRS", {})
    base_dir = txt_dirs.get(supplier)
    if not base_dir:
        raise ValueError(f"未在 BARBOUR['TXT_DIRS'] 中找到 supplier='{supplier}' 的目录配置")

    base = Path(base_dir)
    if not base.exists():
        raise FileNotFoundError(f"TXT 目录不存在：{base}")

    paths = sorted(base.glob("*.txt"))
    mapping = _load_mapping_siteurl_to_code()

    summary = {
        "supplier": supplier,
        "total": len(paths),
        "skipped_code_filename": 0,
        "updated": 0,
        "renamed": 0,
        "no_mapping": 0,
        "skipped_has_valid_code": 0,
        "details": []  # (txt_path, action, note)
    }

    for fp in paths:
        # 1) 文件名是编码 → 跳过
        if _is_code_filename(fp):
            summary["skipped_code_filename"] += 1
            summary["details"].append((fp.as_posix(), "SKIP_FILENAME_IS_CODE", ""))
            continue

        text = fp.read_text(encoding="utf-8", errors="ignore")
        site, url = _extract_site_url(text)
        key = (site.lower(), url)

        code = mapping.get(key)
        if not code:
            summary["no_mapping"] += 1
            summary["details"].append((fp.as_posix(), "NO_MAPPING", f"{site} | {url}"))
            continue

        lines = text.splitlines()
        idx, label, cur_val = _find_product_code_line(lines)

        # 2) 已有有效编码且正确 → 仅重命名
        if cur_val and not _should_overwrite(cur_val):
            # 仅在需要时重命名
            new_fp = _rename_to_code(fp, code)
            if new_fp.name != fp.name:
                summary["renamed"] += 1
                fp = new_fp
                summary["details"].append((fp.as_posix(), "RENAMED", f"{code}"))
            else:
                summary["skipped_has_valid_code"] += 1
                summary["details"].append((fp.as_posix(), "SKIP_ALREADY_VALID_CODE", cur_val))
            continue

        # 3) 覆盖/新增 Product Code 行，统一用 "Product Code: {code}"
        if idx is not None:
            lines[idx] = f"Product Code: {code}"
        else:
            # 不存在该行，追加到文件开头，防止下游解析不到
            lines.insert(0, f"Product Code: {code}")

        new_text = "\n".join(lines)
        fp.write_text(new_text, encoding="utf-8")

        # 4) 重命名为 {code}.txt
        new_fp = _rename_to_code(fp, code)
        if new_fp.name != fp.name:
            summary["renamed"] += 1
            fp = new_fp

        summary["updated"] += 1
        summary["details"].append((fp.as_posix(), "UPDATED_AND_RENAMED", code))

    return summary

# 可选：直接脚本运行时也能用
if __name__ == "__main__":
    import sys, json
    supplier = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = backfill_product_codes_to_txt(supplier)
    print(json.dumps(out, ensure_ascii=False, indent=2))
