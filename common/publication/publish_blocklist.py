# -*- coding: utf-8 -*-
"""
发布黑名单（跨品牌共享，PostgreSQL 表 publish_blocklist）

在名单里且 is_active 的商品编码不会出现在 generate_publication_excels 生成的发布 Excel 中。
  release_on_discount = TRUE  → 供应商端当前未打折时拦截；一旦打折自动放行（可重新发布）
  release_on_discount = FALSE → 永久拦截
  is_active = FALSE           → 已手动解除，不再拦截（记录保留）

运营脚本集中在 ops/blocklist/（初始化迁移、刷新折扣、导出/导入 Excel、手动加入/解除），
说明见 ops/blocklist/__init__.py。
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from cfg.db_config import PGSQL_CONFIG

TABLE = "publish_blocklist"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    code_key                TEXT PRIMARY KEY,           -- UPPER(TRIM(商品编码))，用于匹配
    product_code            TEXT NOT NULL,              -- 原始商品编码
    brand                   TEXT,                       -- 小写品牌 key（判断打折需要）
    original_price_gbp      NUMERIC,                    -- 加入时原价
    discount_price_gbp      NUMERIC,                    -- 加入时折后价
    discount_rate           NUMERIC,                    -- 加入时折扣
    reason                  TEXT,                       -- 最近一次加入原因
    source                  TEXT,                       -- 来源：cross_store_bad / manual / excel_import ...
    release_on_discount     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    block_count             INTEGER NOT NULL DEFAULT 1, -- 被加入黑名单次数
    cur_original_price_gbp  NUMERIC,                    -- 最近一次检查的原价
    cur_discount_price_gbp  NUMERIC,                    -- 最近一次检查的折后价
    cur_is_discounted       BOOLEAN,                    -- 最近一次检查是否打折
    discount_checked_at     TIMESTAMP,
    released_at             TIMESTAMP,                  -- 最近一次因打折放行时间
    note                    TEXT,                       -- 人工备注
    first_blocked_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    last_blocked_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_brand ON {TABLE} (brand);
"""

# 可写入的字段（append / import 使用）
WRITABLE_FIELDS = ["product_code", "brand", "original_price_gbp", "discount_price_gbp", "discount_rate",
                   "reason", "source", "release_on_discount", "note"]


def _connect():
    return psycopg2.connect(**PGSQL_CONFIG)


def _key(code) -> str:
    return str(code).strip().upper()


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def ensure_table(conn=None) -> None:
    own = conn is None
    conn = conn or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    finally:
        if own:
            conn.close()


def read_blocklist(active_only: bool = False) -> pd.DataFrame:
    """读取整张黑名单表。"""
    conn = _connect()
    try:
        ensure_table(conn)
        where = "WHERE is_active" if active_only else ""
        return pd.read_sql(f"SELECT * FROM {TABLE} {where} ORDER BY brand, product_code;", conn)
    finally:
        conn.close()


# ------------------------------------------------------------------ 折扣状态
def refresh_discount_status(only_release_on_discount: bool = True, verbose: bool = True) -> pd.DataFrame:
    """
    查询供应商端当前价格，写回 cur_* 字段；新变为打折的记录写 released_at。
    返回检查结果（code_key, brand, cur_original_price_gbp, cur_discount_price_gbp, cur_is_discounted）。
    """
    from common.pricing.discount_status import fetch_discount_status

    conn = _connect()
    try:
        ensure_table(conn)
        cond = "AND release_on_discount" if only_release_on_discount else ""
        rows = pd.read_sql(
            f"SELECT code_key, brand, cur_is_discounted AS was_discounted FROM {TABLE} "
            f"WHERE is_active {cond} AND brand IS NOT NULL AND TRIM(brand) <> '';", conn)
        if rows.empty:
            return pd.DataFrame()
        codes_by_brand = rows.groupby(rows["brand"].str.strip().str.lower())["code_key"].apply(list).to_dict()
        status = fetch_discount_status(codes_by_brand)
        res = rows.merge(status, on="code_key", how="left")
        found = res["original_price_gbp"].notna()
        res["cur_is_discounted"] = res["is_discounted"].where(found, None)

        values = [
            (r.code_key, _num(r.original_price_gbp), _num(r.discount_price_gbp),
             None if not found[i] else bool(r.cur_is_discounted))
            for i, r in zip(res.index, res.itertuples())
        ]
        with conn.cursor() as cur:
            execute_values(cur, f"""
                UPDATE {TABLE} AS t SET
                    cur_original_price_gbp = v.orig::numeric,
                    cur_discount_price_gbp = v.disc::numeric,
                    cur_is_discounted      = v.is_disc::boolean,
                    discount_checked_at    = NOW(),
                    released_at = CASE WHEN v.is_disc::boolean AND NOT COALESCE(t.cur_is_discounted, FALSE)
                                       THEN NOW() ELSE t.released_at END,
                    updated_at  = NOW()
                FROM (VALUES %s) AS v(code_key, orig, disc, is_disc)
                WHERE t.code_key = v.code_key;
            """, values)
        conn.commit()
    finally:
        conn.close()

    out = res[["code_key", "brand", "original_price_gbp", "discount_price_gbp", "cur_is_discounted", "was_discounted"]] \
        .rename(columns={"original_price_gbp": "cur_original_price_gbp", "discount_price_gbp": "cur_discount_price_gbp"})
    if verbose:
        hit = out[out["cur_is_discounted"] == True]  # noqa: E712
        new = hit[hit["was_discounted"] != True]     # noqa: E712
        print(f"💸 折扣检查 {len(out)} 个：当前打折 {len(hit)} 个（新打折 {len(new)} 个），"
              f"库存表未找到 {int(out['cur_original_price_gbp'].isna().sum())} 个")
        if not new.empty:
            print("   新打折：" + ", ".join(
                f"{r.code_key}({r.cur_discount_price_gbp:g}/{r.cur_original_price_gbp:g})" for r in new.itertuples()))
    return out


# ------------------------------------------------------------------ 发布过滤（generate_publication_excels 使用）
def load_publish_blocklist(check_discount: bool = True) -> set[str]:
    """
    返回当前需要拦截的编码集合（大写）。
    check_discount=True 时先实时刷新折扣状态，release_on_discount 且已打折的编码放行。
    """
    try:
        if check_discount:
            try:
                refresh_discount_status(verbose=True)
            except Exception as e:  # 查价失败时宁可继续拦截（沿用上次检查结果）
                print(f"⚠️ 刷新折扣状态失败，沿用上次检查结果：{e}")
        df = read_blocklist(active_only=True)
    except Exception as e:
        print(f"⚠️ 读取发布黑名单失败，跳过黑名单过滤：{e}")
        return set()

    released = df["release_on_discount"] & (df["cur_is_discounted"] == True)  # noqa: E712
    blocked = set(df.loc[~released, "code_key"])
    print(f"🚫 已加载发布黑名单（表 {TABLE}）：{len(df)} 个编码，打折放行 {int(released.sum())} 个，"
          f"实际拦截 {len(blocked)} 个")
    return blocked


def filter_blocked_codes(codes, blocklist: set[str] | None = None) -> tuple[list, list]:
    """返回 (保留的编码, 被拦截的编码)，保持原有顺序。"""
    if blocklist is None:
        blocklist = load_publish_blocklist()
    kept, blocked = [], []
    for c in codes:
        (blocked if _key(c) in blocklist else kept).append(c)
    if blocked:
        print(f"🚫 黑名单拦截 {len(blocked)} 个编码：{', '.join(map(str, blocked))}")
    return kept, blocked


# ------------------------------------------------------------------ 写入
def upsert_blocklist(rows: Iterable[dict], count_as_new_block: bool = True,
                     reactivate: bool = True) -> tuple[list[str], list[str]]:
    """
    写入/更新黑名单。rows 每项为 {字段: 值}，字段取自 WRITABLE_FIELDS（product_code 必填）。
      新编码 → 插入
      已存在 → 更新传入的非空字段（来源保留首次值）；reactivate=True 时重新激活；
               count_as_new_block=True 时 block_count + 1、刷新 last_blocked_at
    返回 (新增的编码, 已存在而更新的编码)。
    """
    clean: dict[str, dict] = {}
    for r in rows:
        code = str(r.get("product_code") or "").strip()
        if code:
            clean[_key(code)] = {f: r.get(f) for f in WRITABLE_FIELDS} | {"product_code": code}
    if not clean:
        return [], []

    conn = _connect()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(f"SELECT code_key, release_on_discount FROM {TABLE} WHERE code_key = ANY(%s);", (list(clean),))
            existing = dict(cur.fetchall())

            values = []
            for k, r in clean.items():
                rod = r.get("release_on_discount")
                if rod is None or (not isinstance(rod, bool) and pd.isna(rod)):
                    rod = existing.get(k, False)  # 未指定 → 保留原值（新编码默认 FALSE）
                values.append((
                    k, r["product_code"],
                    str(r["brand"]).strip().lower() if r.get("brand") and pd.notna(r["brand"]) else None,
                    _num(r.get("original_price_gbp")), _num(r.get("discount_price_gbp")), _num(r.get("discount_rate")),
                    r.get("reason"), r.get("source"),
                    bool(rod),
                    r.get("note"),
                ))
            inc = "t.block_count + 1" if count_as_new_block else "t.block_count"
            last = "NOW()" if count_as_new_block else "t.last_blocked_at"
            active = "TRUE" if reactivate else "t.is_active"
            execute_values(cur, f"""
                INSERT INTO {TABLE} AS t (code_key, product_code, brand, original_price_gbp, discount_price_gbp,
                                          discount_rate, reason, source, release_on_discount, note)
                VALUES %s
                ON CONFLICT (code_key) DO UPDATE SET
                    product_code        = EXCLUDED.product_code,
                    brand               = COALESCE(EXCLUDED.brand, t.brand),
                    original_price_gbp  = COALESCE(EXCLUDED.original_price_gbp, t.original_price_gbp),
                    discount_price_gbp  = COALESCE(EXCLUDED.discount_price_gbp, t.discount_price_gbp),
                    discount_rate       = COALESCE(EXCLUDED.discount_rate, t.discount_rate),
                    reason              = COALESCE(EXCLUDED.reason, t.reason),
                    source              = COALESCE(t.source, EXCLUDED.source),
                    release_on_discount = EXCLUDED.release_on_discount,
                    note                = COALESCE(EXCLUDED.note, t.note),
                    is_active           = {active},
                    block_count         = {inc},
                    last_blocked_at     = {last},
                    updated_at          = NOW();
            """, values)
        conn.commit()
    finally:
        conn.close()

    added = [clean[k]["product_code"] for k in clean if k not in existing]
    updated = [clean[k]["product_code"] for k in clean if k in existing]
    print(f"🚫 发布黑名单：新增 {len(added)} 个，已存在更新 {len(updated)} 个")
    return added, updated


def set_active(codes: Iterable[str], active: bool, note: str | None = None) -> int:
    """启用（重新拦截）或解除拦截（is_active = FALSE，记录保留）。返回实际变化的行数。"""
    keys = sorted({_key(c) for c in codes if str(c).strip()})
    if not keys:
        return 0
    conn = _connect()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE {TABLE} SET is_active = %s, updated_at = NOW(), note = COALESCE(%s, note)
                WHERE code_key = ANY(%s) AND is_active IS DISTINCT FROM %s;
            """, (active, note, keys, active))
            n = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"✅ 已{'启用拦截' if active else '解除拦截'} {n} 个编码（共请求 {len(keys)} 个）")
    return n


def deactivate_codes(codes: Iterable[str], note: str | None = None) -> int:
    """手动解除拦截（记录保留）。"""
    return set_active(codes, False, note)
