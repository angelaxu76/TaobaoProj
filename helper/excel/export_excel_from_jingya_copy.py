# -*- coding: utf-8 -*-

import re
from pathlib import Path
from openpyxl import Workbook


# ========= 在这里直接修改路径 =========
INPUT_TXT = r"C:\Users\angel\Desktop\YGLD.txt"
OUTPUT_XLSX = r"C:\Users\angel\Desktop\abc.xlsx"

# INPUT_TXT = r"C:\Users\angel\Desktop\WXJ.txt"
# OUTPUT_XLSX = r"C:\Users\angel\Desktop\WXJ.xlsx"
# =====================================


HEADER_SET = {
    "渠道产品名称", "渠道产品ID", "货品ID", "类目", "鲸芽卖家名称",
    "宝贝关联状态", "价格(元)", "库存", "库存类型", "操作"
}


def is_channel_id(s: str) -> bool:
    return bool(re.fullmatch(r"\d{8,}", s))


def read_lines(txt_path: Path):
    with txt_path.open("r", encoding="utf-8") as f:
        raw = [ln.rstrip("\n") for ln in f]
    return [ln.strip() for ln in raw if ln.strip() != ""]


def parse_records(lines):
    rows = []
    i = 0
    n = len(lines)

    while i < n:
        if lines[i] in HEADER_SET or lines[i] in {"--", "关联宝贝"}:
            i += 1
            continue

        j = i
        found = False

        while j < n - 2:
            if is_channel_id(lines[j]) and lines[j + 1] == "--":
                title = " ".join(lines[i:j]).strip()
                channel_id = lines[j]

                if j + 6 < n:
                    category = lines[j + 2]
                    seller = lines[j + 3]
                    status = lines[j + 4]
                    price_str = lines[j + 5]
                    stock_str = lines[j + 6]

                    try:
                        price = float(price_str)
                        stock = int(float(stock_str))
                    except:
                        break

                    rows.append([
                        title,
                        channel_id,
                        category,
                        price,
                        stock,
                        seller,
                        status
                    ])

                    k = j + 7
                    while k < n and lines[k] != "关联宝贝" and lines[k] not in HEADER_SET:
                        k += 1

                    if k < n and lines[k] == "关联宝贝":
                        k += 1

                    i = k
                    found = True
                break
            j += 1

        if not found:
            i += 1

    return rows


def export_to_excel(rows, out_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    ws.append([
        "渠道产品名称",
        "渠道产品ID",
        "类目",
        "价格(元)",
        "库存",
        "鲸芽卖家名称",
        "宝贝关联状态"
    ])

    for r in rows:
        ws.append(r)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main():
    txt_path = Path(INPUT_TXT)
    out_path = Path(OUTPUT_XLSX)

    if not txt_path.exists():
        print(f"❌ 找不到文件: {txt_path}")
        return

    lines = read_lines(txt_path)
    rows = parse_records(lines)

    export_to_excel(rows, out_path)

    print(f"✅ 解析到记录数: {len(rows)}")
    print(f"✅ 已输出文件: {out_path}")


if __name__ == "__main__":
    main()