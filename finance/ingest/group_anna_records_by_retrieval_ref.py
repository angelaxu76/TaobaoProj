import re
import argparse
from pathlib import Path

from PyPDF2 import PdfReader
import csv
from datetime import datetime, date


# -------- 正则模式 --------
# 只匹配标题，不直接抓数字
RE_REF_HEADER_PATTERN = re.compile(
    r"Retrieval\s+Reference\s+number", re.IGNORECASE
)
MERCHANT_PATTERN = re.compile(
    r"Merchant\s+name:\s*(.+)", re.IGNORECASE
)
PROCESSED_ON_PATTERN = re.compile(
    r"Processed on\s+([0-9:APM,\sA-Z]+)", re.IGNORECASE
)

# 抓取像 "9 Oct 2025" 这样的日期
DATE_PATTERN = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
)

# 抓金额： 108.75 (GBP)
GBP_AMOUNT_PATTERN = re.compile(
    r"([0-9]+\.[0-9]{2})\s*\(GBP\)", re.IGNORECASE
)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """读取 PDF 文本（所有页拼到一起）。"""
    reader = PdfReader(str(pdf_path))
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


def detect_is_refund(text: str) -> bool:
    """
    粗略判断是否为退款：
    - 出现 refund / card refund / refund transaction 等关键字
    """
    t = text.lower()
    if "refund" in t:
        return True
    return False


def extract_earliest_date(text: str) -> date | None:
    """
    从文本中找出所有形如 '9 Oct 2025' 的日期，返回最早的一个。
    如果没有找到，返回 None。
    """
    candidates = DATE_PATTERN.findall(text)
    dates: list[date] = []
    for d in candidates:
        try:
            dt = datetime.strptime(d.strip(), "%d %b %Y").date()
            dates.append(dt)
        except ValueError:
            continue
    if not dates:
        return None
    return min(dates)


def extract_retrieval_ref(text: str) -> str | None:
    """
    更鲁棒地提取 Retrieval Reference number：

    1) 先找到 'Retrieval Reference number' 这一段位置；
    2) 从该位置往后截取一小段文本（例如 200 字符）；
    3) 在这段里找所有由 6+ 位数字组成的 token；
    4) 取长度最长的那一个作为 Retrieval Ref。

    对于类似：
        Retrieval Reference
        number
        Amount
        01:35:54 BST,
        9 Oct 2025
        01:35:54 BST,
        9 Oct 2025
        POS 670855 528018096148 41.60 (GBP)

    会找到 670855 和 528018096148，两者中长度最长的是 528018096148。
    """
    header_match = RE_REF_HEADER_PATTERN.search(text)
    if not header_match:
        return None

    start = header_match.end()
    snippet = text[start : start + 300]  # 往后看一小段就够了

    # 找所有 6 位及以上的纯数字 token
    nums = re.findall(r"\b(\d{6,})\b", snippet)
    if not nums:
        return None

    # 按长度排序，选最长的那个
    nums_sorted = sorted(nums, key=lambda x: len(x), reverse=True)
    return nums_sorted[0]


def extract_amount_gbp(text: str) -> str | None:
    """
    提取金额（GBP）：
    - 不再要求前面一定有 "Amount" 单词；
    - 直接全局搜索 "xx.xx (GBP)"，取最后一个。
    """
    matches = GBP_AMOUNT_PATTERN.findall(text)
    if not matches:
        return None
    return matches[-1]


def parse_anna_payment_confirmation(pdf_path: Path) -> dict:
    """
    解析 ANNA 的 payment confirmation PDF，提取关键信息。
    返回 dict，包含：
      - retrieval_ref
      - amount_gbp (字符串)
      - amount (float 或 None)
      - merchant_name
      - processed_on (原始字符串)
      - is_refund (True/False)
      - authorised_date (date 或 None)  # 近似 Authorised on 日期
    """
    text = extract_text_from_pdf(pdf_path)

    # Retrieval Reference number
    retrieval_ref = extract_retrieval_ref(text)

    # Amount
    amount_str = extract_amount_gbp(text)
    try:
        amount = float(amount_str) if amount_str is not None else None
    except ValueError:
        amount = None

    # Merchant name
    merchant_match = MERCHANT_PATTERN.search(text)
    merchant_name = merchant_match.group(1).strip() if merchant_match else None

    # Processed on（暂时不深入解析）
    processed_match = PROCESSED_ON_PATTERN.search(text)
    processed_on = processed_match.group(1).strip() if processed_match else None

    # 是否退款
    is_refund = detect_is_refund(text)

    # 近似 Authorised on：取文本中最早的日期
    authorised_date = extract_earliest_date(text)

    return {
        "retrieval_ref": retrieval_ref,
        "amount_gbp": amount_str,
        "amount": amount,
        "merchant_name": merchant_name,
        "processed_on": processed_on,
        "is_refund": is_refund,
        "authorised_date": authorised_date,
    }


def make_group_dir_name(
    re_ref: str,
    total_pay: float,
    total_refund: float,
    authorised_date: date | None,
) -> str:
    """
    生成最终的文件夹名字：
    例如：2025-10-09__528018096148__Pay_124.80__Refund_38.40

    Windows 不能用的字符有: \ / : * ? " < > |
    所以这里只用数字、字母、下划线和点号。
    """
    if total_pay is None:
        total_pay = 0.0
    if total_refund is None:
        total_refund = 0.0

    pay_str = f"{total_pay:.2f}"
    refund_str = f"{total_refund:.2f}"

    if authorised_date is not None:
        date_str = authorised_date.strftime("%Y-%m-%d")
    else:
        date_str = "NO_DATE"

    if re_ref == "NO_RETRIEVAL_REF":
        return f"{date_str}__NO_RETRIEVAL_REF__Pay_{pay_str}__Refund_{refund_str}"

    return f"{date_str}__{re_ref}__Pay_{pay_str}__Refund_{refund_str}"


def group_pdfs_by_retrieval_ref(
    input_dir: Path,
    output_dir: Path,
    dry_run: bool = False
):
    """
    逻辑分两步：
    1) 扫描所有 PDF，解析信息，先在内存里按 retrieval_ref 聚合总金额（pay/refund）和最早日期
    2) 根据聚合结果生成带“日期 + 汇总金额”的文件夹名，然后把每个 PDF 拷贝过去
    同时输出 index.csv 记录详细信息
    """
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_dir.rglob("*.pdf"))
    print(f"[INFO] Found {len(pdf_files)} PDF(s) in {input_dir}")

    # 先解析所有文件
    all_records = []
    for pdf_path in pdf_files:
        info = parse_anna_payment_confirmation(pdf_path)
        re_ref = info.get("retrieval_ref") or "NO_RETRIEVAL_REF"
        amount = info.get("amount")
        is_refund = info.get("is_refund", False)
        authorised_date = info.get("authorised_date")

        record = {
            "pdf_path": pdf_path,
            "file_name": pdf_path.name,
            "retrieval_ref": re_ref,
            "amount": amount,
            "amount_gbp": info.get("amount_gbp"),
            "is_refund": is_refund,
            "merchant_name": info.get("merchant_name") or "",
            "processed_on": info.get("processed_on") or "",
            "authorised_date": authorised_date,
        }
        all_records.append(record)

    # 按 retrieval_ref 聚合总金额 & 最早日期
    summary: dict[str, dict] = {}
    for rec in all_records:
        re_ref = rec["retrieval_ref"]
        amount = rec["amount"] or 0.0
        is_refund = rec["is_refund"]
        authorised_date = rec["authorised_date"]

        if re_ref not in summary:
            summary[re_ref] = {
                "total_pay": 0.0,
                "total_refund": 0.0,
                "earliest_date": authorised_date,
            }

        if is_refund:
            summary[re_ref]["total_refund"] += amount
        else:
            summary[re_ref]["total_pay"] += amount

        # 更新最早日期
        if authorised_date is not None:
            cur = summary[re_ref]["earliest_date"]
            if cur is None or authorised_date < cur:
                summary[re_ref]["earliest_date"] = authorised_date

    # 第二步：根据 summary 生成每个 ref 的目录名，并拷贝文件
    # 先为每个 ref 计算目录名
    ref_to_dir: dict[str, Path] = {}
    for re_ref, s in summary.items():
        dir_name = make_group_dir_name(
            re_ref,
            total_pay=s["total_pay"],
            total_refund=s["total_refund"],
            authorised_date=s["earliest_date"],
        )
        group_dir = output_dir / dir_name
        ref_to_dir[re_ref] = group_dir

        if not dry_run:
            group_dir.mkdir(parents=True, exist_ok=True)

    # 拷贝文件并记录 index
    index_rows = []
    for rec in all_records:
        re_ref = rec["retrieval_ref"]
        group_dir = ref_to_dir[re_ref]
        target_path = group_dir / rec["file_name"]

        if dry_run:
            print(f"[DRY-RUN] Would copy {rec['pdf_path']} -> {target_path}")
        else:
            data = rec["pdf_path"].read_bytes()
            target_path.write_bytes(data)
            print(f"[OK] Copied {rec['file_name']} -> {group_dir.name}/")

        authorised_date = rec["authorised_date"]
        authorised_date_str = authorised_date.strftime("%Y-%m-%d") if authorised_date else ""

        index_rows.append(
            {
                "file_name": rec["file_name"],
                "source_path": str(rec["pdf_path"]),
                "group_dir": str(group_dir),
                "retrieval_ref": re_ref if re_ref != "NO_RETRIEVAL_REF" else "",
                "amount_gbp": rec["amount_gbp"] or "",
                "is_refund": "YES" if rec["is_refund"] else "NO",
                "merchant_name": rec["merchant_name"],
                "processed_on": rec["processed_on"],
                "authorised_date": authorised_date_str,
            }
        )

    # 写 index.csv
    index_csv_path = output_dir / "index.csv"
    if not dry_run:
        with index_csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "file_name",
                    "source_path",
                    "group_dir",
                    "retrieval_ref",
                    "amount_gbp",
                    "is_refund",
                    "merchant_name",
                    "processed_on",
                    "authorised_date",
                ],
            )
            writer.writeheader()
            writer.writerows(index_rows)

        print(f"[OK] Index CSV written: {index_csv_path}")
    else:
        print("[DRY-RUN] index.csv not written (dry run mode).")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Group ANNA payment PDFs by Retrieval Reference number, "
            "and show date + totals in folder names."
        )
    )
    parser.add_argument(
        "--input-dir", required=True, help="输入 PDF 目录，比如 D:\\ANNA\\Clarks\\raw"
    )
    parser.add_argument(
        "--output-dir", required=True, help="输出分组目录，比如 D:\\ANNA\\Clarks\\grouped"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行：只打印要做什么，不实际复制文件。",
    )

    args = parser.parse_args()
    group_pdfs_by_retrieval_ref(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
