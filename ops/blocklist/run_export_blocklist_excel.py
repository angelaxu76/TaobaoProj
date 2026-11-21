"""
导出发布黑名单到 Excel（默认放到共享盘 E:\\shared\\GEI_SHARED）。
可在 Excel 里修改「启用 / 打折后可发布 / 品牌 / 原因 / 备注」后用 run_import_blocklist_excel.py 导回。
"""
from datetime import date
from pathlib import Path

from config import PUBLISH_BLOCKLIST_DIRS
from common.publication.publish_blocklist import refresh_discount_status
from ops.blocklist.blocklist_excel import export_to_excel

REFRESH_DISCOUNT_FIRST = True   # 导出前先刷新当前折扣状态
OUTPUT_DIR: Path | None = None  # None = PUBLISH_BLOCKLIST_DIRS 中第一个存在的目录


def _default_dir() -> Path:
    for d in PUBLISH_BLOCKLIST_DIRS:
        try:
            if Path(d).is_dir():
                return Path(d)
        except OSError:
            continue
    return Path.cwd()


if __name__ == "__main__":
    if REFRESH_DISCOUNT_FIRST:
        refresh_discount_status()
    out_dir = OUTPUT_DIR or _default_dir()
    path = export_to_excel(out_dir / f"publish_blocklist_export_{date.today():%Y%m%d}.xlsx")
    print(f"✅ 已导出：{path}")
