# -*- coding: utf-8 -*-
"""
按数据库 channel_item_id 判定：
删除鲸芽“货品导出*.xlsx”中重复的【货品名称】行，仅保留与DB匹配的一条。

依赖：pandas, sqlalchemy, psycopg2, openpyxl
从 config.PGSQL_CONFIG 读取连接（支持键名：host/port/user/password/**dbname**）。
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

# ======================= ✅【参数配置区】=======================
GOODS_DIR = Path(r"D:\TB\taofenxiao\goods")
INPUT_PREFIX = "货品导出"
INPUT_SUFFIX = ".xlsx"

DB_TABLE = "clarks_inventory"
DB_CHANNEL_FIELD = "channel_item_id"

COL_NAME = "货品名称"
COL_ID = "货品ID"

# 0 命中时的处理策略： "keep_first"（保留第一条）| "drop_all"（全部删除）
ON_ZERO_MATCH = "keep_first"
# ============================================================

# 读取 DB 配置
from config import PGSQL_CONFIG  # 必须包含 host/port/user/password/dbname

def _pg_url(cfg: dict) -> str:
    """构建 SQLAlchemy 连接串；兼容 dbname 键。"""
    host = cfg.get("host") or cfg.get("HOST")
    port = cfg.get("port") or cfg.get("PORT", 5432)
    user = cfg.get("user") or cfg.get("USER")
    password = cfg.get("password") or cfg.get("PASSWORD")
    # ⚠ 你的 config 用的是 "dbname"
    database = cfg.get("database") or cfg.get("dbname") or cfg.get("DB") or cfg.get("DATABASE")
    if not all([host, port, user, password, database]):
        raise ValueError("PGSQL_CONFIG 缺少必要字段（host/port/user/password/dbname）。")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

def _find_latest(goods_dir: Path, prefix: str, suffix: str) -> Path:
    files = [p for p in goods_dir.glob(f"{prefix}*{suffix}") if p.is_file()]
    if not files:
        raise FileNotFoundError(f"未在 {goods_dir} 找到文件：{prefix}*{suffix}")
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]

def _load_channel_id_set(engine, table: str, field: str) -> set:
    sql = text(f"""
        SELECT DISTINCT {field}
        FROM {table}
        WHERE {field} IS NOT NULL AND {field} <> ''
    """)
    with engine.begin() as conn:
        rows = conn.execute(sql).fetchall()
    return {str(r[0]).strip() for r in rows if r and r[0] is not None}

def _norm(s: pd.Series) -> pd.Series:
    return s.astype(str).fillna("").map(lambda x: x.strip())

def dedup_jingya_goods_by_db(
    goods_dir: Path = GOODS_DIR,
    input_prefix: str = INPUT_PREFIX,
    input_suffix: str = INPUT_SUFFIX,
    db_table: str = DB_TABLE,
    db_channel_field: str = DB_CHANNEL_FIELD,
    col_name: str = COL_NAME,
    col_id: str = COL_ID,
    on_zero_match: str = ON_ZERO_MATCH,
) -> tuple[Path, Path]:
    """
    返回 (去重后Excel路径, 删除清单Excel路径)
    """
    # 1) 找输入
    src = _find_latest(goods_dir, input_prefix, input_suffix)

    # 2) 读 Excel
    df = pd.read_excel(src, dtype=str)
    if col_name not in df.columns or col_id not in df.columns:
        raise KeyError(f"Excel缺少必要列：{col_name} / {col_id}")

    # 保留原始顺序并规范化
    df["_orig_idx"] = range(len(df))
    df["_name_norm"] = _norm(df[col_name])
    df["_id_norm"] = _norm(df[col_id])

    # 3) 读 DB 中的 channel_item_id 集合
    engine = create_engine(_pg_url(PGSQL_CONFIG), future=True)
    channel_ids = _load_channel_id_set(engine, db_table, db_channel_field)

    # 4) 分组处理
    keep_idx = []
    removed_rows = []

    grouped = df.groupby("_name_norm", sort=False)
    for name_val, group in grouped:
        if len(group) == 1:
            keep_idx.extend(group.index.tolist())
            continue

        g = group.sort_values("_orig_idx", ascending=True)
        in_db_mask = g["_id_norm"].map(lambda x: x in channel_ids)
        matched = g[in_db_mask]

        if len(matched) == 1:
            # ✅ 唯一命中：保留它，其余删除
            keep = matched.index[0]
            keep_idx.append(keep)
            for i in g.index.difference([keep]):
                removed_rows.append({**df.loc[i].to_dict(), "删除原因": "同名重复-非系统记录"})
        elif len(matched) > 1:
            # 多命中：保留首条，其余删除
            keep = matched.sort_values("_orig_idx").index[0]
            keep_idx.append(keep)
            for i in g.index.difference([keep]):
                removed_rows.append({**df.loc[i].to_dict(), "删除原因": "同名重复-多命中-已保留首条"})
        else:
            # 0 命中：按策略
            if on_zero_match == "keep_first":
                keep = g.index[0]
                keep_idx.append(keep)
                for i in g.index.difference([keep]):
                    removed_rows.append({**df.loc[i].to_dict(), "删除原因": "同名重复-0命中-保留首条"})
            elif on_zero_match == "drop_all":
                for i in g.index:
                    removed_rows.append({**df.loc[i].to_dict(), "删除原因": "同名重复-0命中-全部删除"})
            else:
                raise ValueError(f"on_zero_match 不支持: {on_zero_match}")

    # 5) 输出
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = goods_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    kept_df = df.loc[sorted(set(keep_idx))].drop(columns=["_orig_idx", "_name_norm", "_id_norm"], errors="ignore")
    removed_df = pd.DataFrame(removed_rows) if removed_rows else pd.DataFrame(columns=list(df.columns) + ["删除原因"])

    out_ok = out_dir / f"货品导出_dedup_by_db_{ts}.xlsx"
    out_rm = out_dir / f"货品导出_deleted_rows_{ts}.xlsx"

    kept_df.to_excel(out_ok, index=False)
    removed_df.to_excel(out_rm, index=False)

    print(f"✅ 输入：{src}")
    print(f"📦 原始行数：{len(df)}")
    print(f"🧹 删除行数：{len(removed_df)}")
    print(f"✅ 保留行数：{len(kept_df)}")
    print(f"💾 输出：{out_ok}")
    print(f"📝 删除清单：{out_rm}")

    return out_ok, out_rm

def main():
    dedup_jingya_goods_by_db()

if __name__ == "__main__":
    main()
