"""
run_send_ecms_notification.py

每次发货后，向 ECMS / 菜鸟发送入库通知邮件。

【直接运行】修改下方"本次发货参数"后运行即可。
【从其他脚本调用】
    from ops.shipping.run_send_ecms_notification import send_ecms_notification
    send_ecms_notification(
        shipment_ref="ECMSTMET20260325",
        couriers=[("884256064655", "Fedex")],
        lp_file=r"C:\...\lp_numbers.txt",
    )
"""

import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, ECMS_RECIPIENTS

# ══════════════════════════════════════════════════════════════════
#  本次发货参数（每次发货前修改这里）
# ══════════════════════════════════════════════════════════════════

SHIP_DATE     = date.today()           # 发货日期，默认今天；手动指定：date(2026, 3, 25)
SHIPMENT_REF  = f"ECMSTMET{SHIP_DATE.strftime('%Y%m%d')}"  # 自动按发货日期生成
COURIERS      = [                      # 快递信息，有几条填几条
    ("884256064655", "Fedex"),
    # ("884256064656", "Parcelforce"),
]
LP_FILE       = r"C:\Users\angel\Desktop\lp_numbers.txt"   # LP 号 txt，每行一个
DRY_RUN       = True                   # True=只预览不发送；False=真正发送

# ══════════════════════════════════════════════════════════════════


def _next_business_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _load_lp(lp_file: str) -> list[str]:
    with open(lp_file, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def send_ecms_notification(
    shipment_ref: str,
    couriers: list[tuple[str, str]],
    lp_file: str,
    ship_date: date | None = None,
    dry_run: bool = False,
) -> None:
    """
    Parameters
    ----------
    shipment_ref : 批次参考号，如 "ECMSTMET20260325"
    couriers     : [(快递单号, 快递公司), ...]，如 [("884256064655", "Fedex")]
    lp_file      : LP 包裹号 txt 文件路径，每行一个
    ship_date    : 发货日期，默认今天
    dry_run      : True 只打印预览，False 真正发送
    """
    if ship_date is None:
        ship_date = date.today()

    lp_numbers    = _load_lp(lp_file)
    total_parcels = len(lp_numbers)
    box_count     = len(couriers)
    arrival_date  = _next_business_day(ship_date)

    subject = f"BC+TM+Eminzora Trade Ltd+LHR+{shipment_ref}+{total_parcels}"

    courier_blocks = [
        f"Box Tracking Number: {no}\nCourier Name: {name}"
        for no, name in couriers
    ]

    body = (
        f"Supplier Name: Eminzora Trade Ltd\n"
        f"Total no. of parcels: {total_parcels}\n"
        f"Mode of transport & quantity: {box_count} Box\n"
        f"Estimated arrival time: {arrival_date.strftime('%Y-%m-%d')}\n"
        f"\n\n"
        f"{chr(10).join(courier_blocks)}\n"
        f"\n"
        f"Packing list & Export Declaration Information Collection-ECM：\n"
        f"{chr(10).join(lp_numbers)}\n"
    )

    print("=" * 60)
    print(f"收件人: {', '.join(ECMS_RECIPIENTS)}")
    print(f"标  题: {subject}")
    print("-" * 60)
    print(body)
    print("=" * 60)

    if dry_run:
        print("[DRY RUN] 未发送。将 DRY_RUN 改为 False 后重新运行以真正发送。")
        return

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(ECMS_RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, ECMS_RECIPIENTS, msg.as_string())

    print(f"[OK] 邮件已发送至 {len(ECMS_RECIPIENTS)} 个收件人。")


def main():
    send_ecms_notification(
        shipment_ref = SHIPMENT_REF,
        couriers     = [
            ("GI004896092GB", "Parcelforce"),
            ("GI004896027GB", "Parcelforce"),
        ],
        lp_file      = r"G:\temp\lp_numbers.txt",
        ship_date    = SHIP_DATE,
        dry_run      = False,
    )

    # send_ecms_notification(
    #     shipment_ref = SHIPMENT_REF,
    #     couriers     = [
    #         ("UH7209805", "Parcelforce"),
    #     ],
    #     lp_file      = r"G:\temp\lp_numbers.txt",
    #     ship_date    = SHIP_DATE,
    #     dry_run      = False,
    # )



if __name__ == "__main__":
    main()
