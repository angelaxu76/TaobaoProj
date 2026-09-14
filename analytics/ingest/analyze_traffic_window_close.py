from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG

CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"

VALID_METRICS = {"visitors", "pageviews"}
METRIC_LABEL = {"visitors": "访客数", "pageviews": "浏览量"}

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
matplotlib.rcParams["axes.unicode_minus"] = False


@dataclass
class WindowCloseConfig:
    weeks: int = 4                      # "新品"的定义：只分析发布时间在最近 N 周内的商品
    metric: str = "visitors"            # "visitors"（访客数）或 "pageviews"（浏览量）
    brand: Optional[str] = None         # None = 不限品牌
    max_day: int = 20                   # 分析发布后前多少天的"零流量 -> 是否后续复活"情况
    trailing_check_days: int = 7        # 判断"之后还有没有流量"时，往后看多少天
    revive_threshold_pct: float = 5.0   # 复活概率低于此阈值，视为窗口已关闭
    min_sample_size: int = 20           # 某一天零流量的样本数低于此值，判断不够可靠
    output_path: Optional[str] = None   # Excel 输出路径，None 则不导出
    chart_path: Optional[str] = None    # 图表 PNG 输出路径，None 则不出图


def _fetch(cfg: WindowCloseConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    只取发布时间在近 cfg.weeks 周内的商品（严格意义上的"新品"）。
    注意：商品越新，能往后观察的天数就越少——第 D 天的复活概率只用"已经过了
    D + trailing_check_days 天"的那部分新品来算（见 _compute_revival_curve），
    不会混入发布已久的老商品。
    """
    if cfg.metric not in VALID_METRICS:
        raise ValueError(f"metric 必须是 {VALID_METRICS} 之一，收到：{cfg.metric}")

    cutoff_date = date.today() - timedelta(weeks=cfg.weeks)
    params = {"cutoff_date": cutoff_date, "brand": cfg.brand}
    brand_filter = "AND LOWER(TRIM(c.brand)) = LOWER(TRIM(%(brand)s))" if cfg.brand else ""

    items_sql = f"""
        SELECT
            c.current_item_id AS item_id,
            c.product_code,
            c.item_name,
            c.brand,
            c.publication_date
        FROM {CATALOG_TABLE} c
        WHERE c.publication_date IS NOT NULL
          AND c.publication_date >= %(cutoff_date)s
          AND c.publication_date <= CURRENT_DATE
          {brand_filter}
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        items_df = pd.read_sql(items_sql, conn, params=params)
        if items_df.empty:
            return items_df, pd.DataFrame(columns=["item_id", "day_no", "traffic"])

        items_df["elapsed_days"] = (pd.Timestamp(date.today()) - pd.to_datetime(items_df["publication_date"])).dt.days + 1

        item_ids = [int(x) for x in items_df["item_id"].tolist()]
        daily_sql = f"""
            SELECT
                d.item_id,
                (d.stat_date - c.publication_date + 1) AS day_no,
                SUM(COALESCE(d.{cfg.metric}, 0)) AS traffic
            FROM {DAILY_TABLE} d
            JOIN {CATALOG_TABLE} c ON c.current_item_id = d.item_id
            WHERE d.item_id = ANY(%(item_ids)s)
              AND d.stat_date >= c.publication_date
            GROUP BY d.item_id, (d.stat_date - c.publication_date + 1)
        """
        daily_df = pd.read_sql(daily_sql, conn, params={"item_ids": item_ids})
        return items_df, daily_df
    finally:
        conn.close()


def _compute_revival_curve(items_df: pd.DataFrame, daily_df: pd.DataFrame,
                            cfg: WindowCloseConfig) -> pd.DataFrame:
    """
    对每个截止天数 D，只用"发布至今已经过了 D + trailing_check_days 天"的那部分新品来算
    （仍然全部来自近 cfg.weeks 周的新品池，不会混入更早发布的老商品；只是同一批新品里，
    越老的那一部分，才有资格验证越大的 D）：
      eligible_count  = 有资格验证第 D 天的新品数（发布已满 D+trailing_check_days 天）
      zero_through_D  = 这些商品里，发布后第1~D天累计流量为0的商品数
      revived         = zero_through_D 里，在第 D+1 ~ D+trailing_check_days 天又出现流量的商品数
      revive_rate_pct = revived / zero_through_D * 100
    """
    rows = []
    for d in range(1, cfg.max_day + 1):
        eligible_ids = items_df.loc[items_df["elapsed_days"] >= d + cfg.trailing_check_days, "item_id"]
        eligible_count = len(eligible_ids)
        if eligible_count == 0:
            rows.append({
                "day_no": d, "eligible_count": 0,
                "zero_through_day_count": 0, "revived_count": 0, "revive_rate_pct": None,
            })
            continue

        daily_eligible = daily_df[daily_df["item_id"].isin(eligible_ids)]

        cum_through_d = (
            daily_eligible[daily_eligible["day_no"] <= d]
            .groupby("item_id")["traffic"].sum()
            .reindex(eligible_ids, fill_value=0)
        )
        zero_mask = cum_through_d == 0
        zero_count = int(zero_mask.sum())

        after_window = (
            daily_eligible[(daily_eligible["day_no"] > d) & (daily_eligible["day_no"] <= d + cfg.trailing_check_days)]
            .groupby("item_id")["traffic"].sum()
            .reindex(eligible_ids, fill_value=0)
        )
        revived_mask = zero_mask & (after_window > 0)
        revived_count = int(revived_mask.sum())

        revive_rate = round(revived_count / zero_count * 100, 1) if zero_count > 0 else None
        rows.append({
            "day_no": d,
            "eligible_count": eligible_count,
            "zero_through_day_count": zero_count,
            "revived_count": revived_count,
            "revive_rate_pct": revive_rate,
        })
    return pd.DataFrame(rows)


def _compute_item_detail(items_df: pd.DataFrame, daily_df: pd.DataFrame,
                          cfg: WindowCloseConfig) -> pd.DataFrame:
    item_ids = items_df["item_id"]

    early_traffic = (
        daily_df[daily_df["day_no"] <= cfg.max_day]
        .groupby("item_id")["traffic"].sum()
        .reindex(item_ids, fill_value=0)
    )
    active = daily_df[daily_df["traffic"] > 0]
    last_active_day = active.groupby("item_id")["day_no"].max().reindex(item_ids, fill_value=0).astype(int)

    detail = items_df.copy()
    detail["early_window_traffic"] = early_traffic.values
    detail["last_active_day"] = last_active_day.values
    detail["ever_had_traffic"] = detail["last_active_day"] > 0
    return detail


def _find_close_day(curve: pd.DataFrame, cfg: WindowCloseConfig) -> Optional[int]:
    reliable = curve[curve["zero_through_day_count"] >= cfg.min_sample_size]
    hit = reliable[reliable["revive_rate_pct"] <= cfg.revive_threshold_pct]
    if hit.empty:
        return None
    return int(hit["day_no"].iloc[0])


def _plot_revival_panel(ax, curve: pd.DataFrame, cfg: WindowCloseConfig, close_day: Optional[int]) -> None:
    ax.plot(curve["day_no"], curve["revive_rate_pct"], color="#C44E52", marker="o", linewidth=2,
            label="复活概率（%）")
    ax.axhline(cfg.revive_threshold_pct, color="#999999", linestyle="--", linewidth=1,
                label=f"阈值 {cfg.revive_threshold_pct}%")
    if close_day is not None:
        ax.axvline(close_day, color="#4C72B0", linestyle="--", linewidth=1.5,
                    label=f"建议窗口关闭日 ≈ 第{close_day}天")
    ax.set_xlabel("到第几天为止仍是零流量")
    ax.set_ylabel("之后又出现流量的概率（%）")
    ax.set_title(f"零流量后的复活概率（往后看{cfg.trailing_check_days}天）")
    ax.set_xticks(curve["day_no"])
    ax.set_ylim(bottom=0)

    ax2 = ax.twinx()
    ax2.bar(curve["day_no"], curve["zero_through_day_count"], color="#4C72B0", alpha=0.15,
            label="样本量（仍零流量的商品数）")
    ax2.set_ylabel("样本量（商品数）")

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)


def _plot_last_active_panel(ax, detail: pd.DataFrame, cfg: WindowCloseConfig) -> None:
    ever = detail[detail["ever_had_traffic"]]
    never_pct = round((1 - len(ever) / len(detail)) * 100, 1) if len(detail) else 0

    # 用商品实际观察到的最大天数（而不是固定的 max_day+trailing_check_days），
    # 避免在窗口边界处出现"因为没抓那么远的数据"造成的人为堆积
    max_observed_day = int(ever["last_active_day"].max()) if not ever.empty else cfg.max_day
    dist = (
        ever["last_active_day"]
        .value_counts()
        .reindex(range(1, max_observed_day + 1), fill_value=0)
        .sort_index()
    )
    cum_pct = (dist.cumsum() / dist.sum() * 100).round(1) if dist.sum() else dist.cumsum()

    ax.bar(dist.index, dist.values, color="#55A868", alpha=0.85, label=f"商品数量（n={len(ever)}）")
    ax.set_xlabel("最后一次出现流量是发布后第几天")
    ax.set_ylabel("商品数量")
    ax.set_title(f"流量最后一次出现的天数分布（另有{never_pct}%商品全程零流量）")

    ax2 = ax.twinx()
    ax2.plot(dist.index, cum_pct.values, color="#DD8452", marker="o", markersize=3, label="累计占比")
    ax2.set_ylabel("累计占比（%）")
    ax2.set_ylim(0, 105)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="center right", fontsize=8)


def _plot_charts(curve: pd.DataFrame, detail: pd.DataFrame, cfg: WindowCloseConfig,
                  close_day: Optional[int]) -> None:
    if not cfg.chart_path or curve.empty:
        return
    Path(cfg.chart_path).parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(17, 5.5))
    _plot_revival_panel(ax1, curve, cfg, close_day)
    _plot_last_active_panel(ax2, detail, cfg)

    fig.tight_layout()
    fig.savefig(cfg.chart_path, dpi=150)
    plt.close(fig)


def _build_field_doc(cfg: WindowCloseConfig) -> pd.DataFrame:
    rows = [
        ("复活概率明细", "day_no", "截止到发布后第几天"),
        ("复活概率明细", "eligible_count",
         f"有资格验证这一天的新品数（发布已满 day_no+{cfg.trailing_check_days} 天，仍属于近{cfg.weeks}周新品池，只是这批里更早发布的那部分）"),
        ("复活概率明细", "zero_through_day_count", "eligible_count 里，到这一天为止累计流量仍为0的商品数（复活概率的样本量）"),
        ("复活概率明细", "revived_count",
         f"这些零流量商品里，接下来{cfg.trailing_check_days}天内又出现流量的商品数"),
        ("复活概率明细", "revive_rate_pct", "revived_count / zero_through_day_count，即“复活概率”"),
        ("商品明细", "item_id", "淘宝商品ID"),
        ("商品明细", "product_code", "商家编码/货号"),
        ("商品明细", "item_name", "商品标题"),
        ("商品明细", "brand", "品牌"),
        ("商品明细", "publication_date", "发布/上架日期"),
        ("商品明细", "elapsed_days", "距今天已经过了多少天（商品当前的“年龄”）"),
        ("商品明细", "early_window_traffic", f"发布后前{cfg.max_day}天的累计流量（发布不满{cfg.max_day}天的商品只是目前已有的部分）"),
        ("商品明细", "last_active_day", "最后一次出现非零流量是发布后第几天；0=全程零流量"),
        ("商品明细", "ever_had_traffic", "该商品目前为止是否出现过流量"),
    ]
    return pd.DataFrame(rows, columns=["所在Sheet", "字段", "含义"])


def _export_excel(curve: pd.DataFrame, detail: pd.DataFrame, cfg: WindowCloseConfig) -> None:
    if not cfg.output_path:
        return
    Path(cfg.output_path).parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
        _build_field_doc(cfg).to_excel(writer, index=False, sheet_name="字段说明")
        curve.to_excel(writer, index=False, sheet_name="复活概率明细")
        detail.to_excel(writer, index=False, sheet_name="商品明细")

    if cfg.chart_path and Path(cfg.chart_path).exists():
        from openpyxl import load_workbook
        from openpyxl.drawing.image import Image as XLImage

        wb = load_workbook(cfg.output_path)
        ws = wb["复活概率明细"]
        ws.add_image(XLImage(cfg.chart_path), "F2")
        wb.save(cfg.output_path)


def analyze_traffic_window_close(cfg: WindowCloseConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    只用近 cfg.weeks 周内发布的新品，找出"新品流量扶持窗口"大致在第几天关闭：
    对每个截止天数 D，在这批新品里挑出"已经过了 D + trailing_check_days 天"的部分
    （仍然全是新品池里的商品，只是这批里更早发布的那一部分），看它们发布后前 D 天
    是否零流量、以及零流量的商品在 D 天之后是否又出现流量。这个"复活概率"降到阈值
    以下的最早那一天，就是建议的"窗口关闭日"。
    """
    items_df, daily_df = _fetch(cfg)
    metric_label = METRIC_LABEL[cfg.metric]

    if items_df.empty:
        print(f"⚠️ 近 {cfg.weeks} 周内没有发布任何商品，无法分析")
        return pd.DataFrame(), pd.DataFrame()

    curve = _compute_revival_curve(items_df, daily_df, cfg)
    detail = _compute_item_detail(items_df, daily_df, cfg)
    close_day = _find_close_day(curve, cfg)

    _plot_charts(curve, detail, cfg, close_day)
    _export_excel(curve, detail, cfg)

    print(f"✅ 分析完成：近 {cfg.weeks} 周内发布的新品共 {len(items_df)} 个（指标={metric_label}）")
    max_eligible = int(curve["eligible_count"].max()) if not curve.empty else 0
    min_eligible = int(curve.loc[curve["day_no"] == cfg.max_day, "eligible_count"].iloc[0]) if not curve.empty else 0
    print(f"   第1天可验证样本 {max_eligible} 个，第{cfg.max_day}天可验证样本 {min_eligible} 个"
          f"（商品越新，能验证到的天数越短，这是新品池天然的限制）")
    if close_day is not None:
        row = curve[curve["day_no"] == close_day].iloc[0]
        print(f"   建议窗口关闭日 ≈ 第 {close_day} 天：到这天仍零流量的新品（样本 {int(row['zero_through_day_count'])} 个），"
              f"之后 {cfg.trailing_check_days} 天内复活概率仅 {row['revive_rate_pct']}%")
        print("   → 也就是说，如果一个新品发布后第{}天还没有任何流量，基本可以判断后续也不会再有了。".format(close_day))
    else:
        print(f"   ⚠️ 在统计的前 {cfg.max_day} 天内，复活概率没有降到 {cfg.revive_threshold_pct}% 以下"
              f"（或样本量不足 {cfg.min_sample_size}），在“近{cfg.weeks}周新品”这个范围内看不到明确的窗口关闭点")
    if cfg.output_path:
        print(f"   Excel：{cfg.output_path}")
    if cfg.chart_path:
        print(f"   图表：{cfg.chart_path}")

    return curve, detail


if __name__ == "__main__":
    analyze_traffic_window_close(
        WindowCloseConfig(
            weeks=4,
            metric="visitors",
            brand=None,
            max_day=20,
            trailing_check_days=7,
            output_path=r"D:\TB\analytics\export\traffic_window_close.xlsx",
            chart_path=r"D:\TB\analytics\export\traffic_window_close.png",
        )
    )
