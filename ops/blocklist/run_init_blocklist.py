"""
建表 publish_blocklist，并把旧的 Excel 黑名单（PUBLISH_BLOCKLIST_DIRS 下的 publish_blocklist.xlsx）迁移进来。
可重复执行：已存在的编码只补充空字段，不增加加入次数。旧 Excel 不会被修改或删除。
"""
from pathlib import Path

import pandas as pd

from config import PUBLISH_BLOCKLIST_DIRS, PUBLISH_BLOCKLIST_FILENAME
from common.publication.publish_blocklist import ensure_table, upsert_blocklist, read_blocklist
from ops.blocklist.blocklist_excel import to_bool

OLD_COLUMNS = {"商品编码": "product_code", "品牌": "brand", "原价": "original_price_gbp",
               "打折后价格": "discount_price_gbp", "折扣": "discount_rate", "原因": "reason",
               "打折后可发布": "release_on_discount"}


def find_old_excel() -> Path | None:
    for d in PUBLISH_BLOCKLIST_DIRS:
        try:
            p = Path(d) / PUBLISH_BLOCKLIST_FILENAME
            if p.exists():
                return p
        except OSError:
            continue
    return None


if __name__ == "__main__":
    ensure_table()
    print("✅ 表 publish_blocklist 已就绪")

    old = find_old_excel()
    if old is None:
        print("ℹ️ 未找到旧 Excel 黑名单，跳过迁移")
    else:
        df = pd.read_excel(old, dtype=str)
        df = df[[c for c in OLD_COLUMNS if c in df.columns]].rename(columns=OLD_COLUMNS)
        if "release_on_discount" in df.columns:
            df["release_on_discount"] = df["release_on_discount"].map(to_bool)
        for c in ("original_price_gbp", "discount_price_gbp", "discount_rate"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.astype(object).where(df.notna(), None)
        rows = [r | {"source": "excel_migration"} for r in df.to_dict("records")]
        print(f"📥 从旧 Excel 迁移 {len(rows)} 行：{old}")
        upsert_blocklist(rows, count_as_new_block=False)

    t = read_blocklist()
    print(f"📊 当前表内 {len(t)} 个编码（启用 {int(t['is_active'].sum())}，打折后可发布 {int(t['release_on_discount'].sum())}）")
    if not t.empty:
        print(t.groupby("brand", dropna=False).size().to_string())
