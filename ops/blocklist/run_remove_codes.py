"""
手动解除商品编码的发布拦截（is_active = FALSE，记录保留，可再用 run_add_codes 重新加入）。
"""
from pathlib import Path

from common.publication.publish_blocklist import deactivate_codes

CODES: list[str] = [
    # "K100000-001",
]
INPUT_TXT: Path | None = None       # 或者一行一个编码的 TXT（UTF-8），与 CODES 合并
NOTE: str | None = "手动解除"

if __name__ == "__main__":
    codes = list(CODES)
    if INPUT_TXT:
        codes += [l.strip() for l in INPUT_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not codes:
        print("⚠️ 没有要解除的编码，请先填写 CODES 或 INPUT_TXT")
    else:
        deactivate_codes(codes, note=NOTE)
