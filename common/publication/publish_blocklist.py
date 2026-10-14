# -*- coding: utf-8 -*-
"""
发布黑名单（跨品牌共享，Excel 格式）

列：商品编码 | 品牌 | 原价 | 打折后价格 | 折扣 | 无访问被删除次数 | 原因
只有「商品编码」用于过滤，其余列仅作记录，方便了解加入原因。
编码比较时忽略大小写和首尾空格。

文件位置：按 PUBLISH_BLOCKLIST_DIRS 顺序取第一个存在的目录下的
publish_blocklist.xlsx（VM 内为 \\vmware-host\\Shared Folders\\VMShared，
宿主机为 E:\\shared\\GEI_SHARED）。文件不存在时自动创建空模板，视为空名单。
"""
from pathlib import Path

import pandas as pd

from config import PUBLISH_BLOCKLIST_DIRS, PUBLISH_BLOCKLIST_FILENAME

CODE_COL = "商品编码"
BLOCKLIST_COLUMNS = [CODE_COL, "品牌", "原价", "打折后价格", "折扣", "无访问被删除次数", "原因"]


def get_blocklist_path() -> Path | None:
    for d in PUBLISH_BLOCKLIST_DIRS:
        try:
            if Path(d).is_dir():
                return Path(d) / PUBLISH_BLOCKLIST_FILENAME
        except OSError:
            continue
    return None


def create_blocklist_template(path: Path) -> None:
    """创建只有表头的空黑名单 Excel。"""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(columns=BLOCKLIST_COLUMNS).to_excel(writer, index=False, sheet_name="blocklist")
        ws = writer.sheets["blocklist"]
        for col, width in zip("ABCDEFG", [18, 12, 10, 12, 8, 16, 40]):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"


def load_publish_blocklist() -> set[str]:
    path = get_blocklist_path()
    if path is None:
        print("⚠️ 未找到发布黑名单目录，跳过黑名单过滤")
        return set()
    if not path.exists():
        create_blocklist_template(path)
        print(f"ℹ️ 发布黑名单不存在，已创建空模板：{path}")
        return set()

    df = pd.read_excel(path, dtype={CODE_COL: str})
    if CODE_COL not in df.columns:
        raise ValueError(f"❌ 发布黑名单缺少「{CODE_COL}」列：{path}")

    codes = {
        c.strip().upper()
        for c in df[CODE_COL].dropna().astype(str)
        if c.strip()
    }
    print(f"🚫 已加载发布黑名单：{path}（{len(codes)} 个编码）")
    return codes


def filter_blocked_codes(codes, blocklist: set[str] | None = None) -> tuple[list, list]:
    """返回 (保留的编码, 被拦截的编码)，保持原有顺序。"""
    if blocklist is None:
        blocklist = load_publish_blocklist()
    kept, blocked = [], []
    for c in codes:
        (blocked if str(c).strip().upper() in blocklist else kept).append(c)
    if blocked:
        print(f"🚫 黑名单拦截 {len(blocked)} 个编码：{', '.join(map(str, blocked))}")
    return kept, blocked


def append_to_blocklist(rows: list[dict]) -> tuple[list[str], list[str]]:
    """
    追加记录到发布黑名单。rows 每项为 {列名: 值}，列名取自 BLOCKLIST_COLUMNS。
    已在名单里的编码不重复追加。写入前把原文件备份为 *.bak.xlsx。
    返回 (新增的编码, 已存在而跳过的编码)。
    """
    path = get_blocklist_path()
    if path is None:
        raise FileNotFoundError(f"❌ 未找到发布黑名单目录：{PUBLISH_BLOCKLIST_DIRS}")
    if not path.exists():
        create_blocklist_template(path)

    df = pd.read_excel(path, dtype={CODE_COL: str})
    existing = {c.strip().upper() for c in df[CODE_COL].dropna().astype(str) if c.strip()}

    added, skipped, new_rows = [], [], []
    for r in rows:
        code = str(r.get(CODE_COL) or "").strip()
        if not code:
            continue
        if code.upper() in existing:
            skipped.append(code)
            continue
        existing.add(code.upper())
        added.append(code)
        new_rows.append({c: r.get(c) for c in BLOCKLIST_COLUMNS})

    if not new_rows:
        return added, skipped

    path.with_suffix(".bak.xlsx").write_bytes(path.read_bytes())
    out = pd.concat([df, pd.DataFrame(new_rows, columns=BLOCKLIST_COLUMNS)], ignore_index=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="blocklist")
        ws = writer.sheets["blocklist"]
        for col, width in zip("ABCDEFG", [18, 12, 10, 12, 8, 16, 40]):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"
    print(f"🚫 已追加 {len(added)} 个编码到发布黑名单：{path}（已存在跳过 {len(skipped)} 个）")
    return added, skipped
