from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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
class TrafficPeakConfig:
    weeks: int = 4                      # 只分析发布时间在最近 N 周内的商品
    metric: str = "visitors"            # "visitors"（访客数）或 "pageviews"（浏览量）
    brand: Optional[str] = None         # None = 不限品牌
    min_total_traffic: int = 1          # 累计流量低于此值的商品无有效峰值，排除出分布
    early_window_days: int = 14         # "新品早期流量"统计窗口（发布后第几天内），默认两周
    output_path: Optional[str] = None   # Excel 输出路径（明细 + 分布表），None 则不导出
    chart_path: Optional[str] = None    # 分布图 PNG 输出路径，None 则不出图


def _fetch_daily_traffic(cfg: TrafficPeakConfig) -> pd.DataFrame:
    if cfg.metric not in VALID_METRICS:
        raise ValueError(f"metric 必须是 {VALID_METRICS} 之一，收到：{cfg.metric}")

    cutoff_date = date.today() - timedelta(weeks=cfg.weeks)
    params = {"cutoff_date": cutoff_date, "brand": cfg.brand}
    brand_filter = "AND LOWER(TRIM(c.brand)) = LOWER(TRIM(%(brand)s))" if cfg.brand else ""

    sql = f"""
        WITH pub AS (
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
        )
        SELECT
            p.item_id,
            p.product_code,
            p.item_name,
            p.brand,
            p.publication_date,
            d.stat_date,
            (d.stat_date - p.publication_date + 1) AS day_no,
            SUM(COALESCE(d.{cfg.metric}, 0)) AS traffic
        FROM pub p
        JOIN {DAILY_TABLE} d ON d.item_id = p.item_id
        WHERE d.stat_date >= p.publication_date
        GROUP BY p.item_id, p.product_code, p.item_name, p.brand, p.publication_date, d.stat_date
        ORDER BY p.item_id, d.stat_date;
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def _compute_summary(df: pd.DataFrame, cfg: TrafficPeakConfig) -> pd.DataFrame:
    cols = ["item_id", "product_code", "item_name", "brand", "publication_date",
            "days_observed", "total_traffic", "peak_day", "peak_traffic",
            "early_window_traffic", "early_window_complete"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    totals = df.groupby("item_id")["traffic"].sum().rename("total_traffic")
    observed = df.groupby("item_id")["day_no"].max().rename("days_observed")
    early = (
        df[df["day_no"] <= cfg.early_window_days]
        .groupby("item_id")["traffic"].sum()
        .rename("early_window_traffic")
    )

    # 每个商品流量最高的一天；若多天并列最高，取最早出现的一天
    df_sorted = df.sort_values("day_no")
    idx = df_sorted.groupby("item_id")["traffic"].idxmax()
    peak = df_sorted.loc[idx, ["item_id", "product_code", "item_name", "brand",
                                "publication_date", "day_no", "traffic"]].rename(
        columns={"day_no": "peak_day", "traffic": "peak_traffic"}
    )

    result = (
        peak.merge(totals, on="item_id")
        .merge(observed, on="item_id")
        .merge(early, on="item_id", how="left")
    )
    result["early_window_traffic"] = result["early_window_traffic"].fillna(0).astype(int)

    # 是否已发布满 early_window_days 天（未满则该商品的早期流量还没统计完整，不能直接和其它商品比）
    pub_date = pd.to_datetime(result["publication_date"]).dt.date
    elapsed_days = pub_date.apply(lambda d: (date.today() - d).days + 1)
    result["early_window_complete"] = elapsed_days >= cfg.early_window_days

    result = result[result["total_traffic"] >= cfg.min_total_traffic]
    return result.sort_values("peak_day").reset_index(drop=True)[cols]


def _build_distribution(peak_df: pd.DataFrame) -> pd.DataFrame:
    cols = ["peak_day", "product_count", "pct", "cum_pct"]
    if peak_df.empty:
        return pd.DataFrame(columns=cols)

    max_day = int(peak_df["peak_day"].max())
    dist = (
        peak_df.groupby("peak_day")
        .size()
        .reindex(range(1, max_day + 1), fill_value=0)
        .rename("product_count")
        .reset_index()
        .rename(columns={"index": "peak_day"})
    )
    total = dist["product_count"].sum()
    dist["pct"] = (dist["product_count"] / total * 100).round(1)
    dist["cum_pct"] = dist["pct"].cumsum().round(1)
    return dist[cols]


def _plot_peak_day_panel(ax, peak_df: pd.DataFrame, dist: pd.DataFrame, cfg: TrafficPeakConfig) -> None:
    """左图：直方图（每个到达峰值的天数 -> 商品数量）+ 正态分布拟合曲线。"""
    metric_label = METRIC_LABEL[cfg.metric]
    values = peak_df["peak_day"].astype(float)
    mean = float(values.mean())
    std = float(values.std(ddof=0))
    n = len(values)

    ax.bar(dist["peak_day"], dist["product_count"], color="#4C72B0", alpha=0.85,
           label=f"商品数量（n={n}）")
    ax.set_xlabel("发布后第几天流量达到峰值")
    ax.set_ylabel("商品数量")
    ax.set_title(f"峰值出现在第几天（近 {cfg.weeks} 周内发布，指标={metric_label}）")
    ax.set_xticks(dist["peak_day"])

    if std > 0:
        x = np.linspace(dist["peak_day"].min(), dist["peak_day"].max(), 200)
        pdf = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
        # bin 宽度为 1 天，把概率密度换算成商品数量的尺度，方便与柱状图叠加对比
        ax.plot(x, pdf * n, color="#DD8452", linewidth=2,
                label=f"正态拟合 (μ={mean:.1f}, σ={std:.1f})")
        ax.axvline(mean, color="#DD8452", linestyle="--", linewidth=1, alpha=0.7)

    ax.legend(loc="upper right", fontsize=9)


def _plot_log_hist_panel(ax, values: pd.Series, color: str, fit_color: str,
                          title: str, xlabel: str) -> None:
    """
    通用面板：数值跨度很大时，按对数（指数级）刻度分箱画直方图，
    并在对数空间拟合正态曲线（即对原始数值做对数正态拟合）。
    """
    traffic = values.astype(float).clip(lower=1)
    log_traffic = np.log10(traffic)
    n = len(traffic)
    mean_log = float(log_traffic.mean())
    std_log = float(log_traffic.std(ddof=0))

    n_bins = min(30, max(10, n // 20))
    counts, edges, _ = ax.hist(
        log_traffic, bins=n_bins, color=color, alpha=0.85,
        label=f"商品数量（n={n}）",
    )
    ax.set_xlabel(xlabel)
    ax.set_ylabel("商品数量")
    ax.set_title(title)

    # 刻度显示为原始数值（1 / 10 / 100 / 1000 ...），而非 log 值
    lo, hi = int(np.floor(log_traffic.min())), int(np.ceil(log_traffic.max()))
    ticks = list(range(lo, hi + 1))
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{10 ** t:,.0f}" for t in ticks])

    if std_log > 0:
        bin_width = edges[1] - edges[0]
        x = np.linspace(edges[0], edges[-1], 200)
        pdf = np.exp(-0.5 * ((x - mean_log) / std_log) ** 2) / (std_log * np.sqrt(2 * np.pi))
        ax.plot(x, pdf * n * bin_width, color=fit_color, linewidth=2,
                label=f"对数正态拟合 (中位数≈{10 ** mean_log:,.0f})")
        ax.axvline(mean_log, color=fit_color, linestyle="--", linewidth=1, alpha=0.7)

    ax.legend(loc="upper right", fontsize=9)


def _plot_charts(peak_df: pd.DataFrame, dist: pd.DataFrame, cfg: TrafficPeakConfig) -> None:
    if not cfg.chart_path or dist.empty:
        return
    Path(cfg.chart_path).parent.mkdir(parents=True, exist_ok=True)
    metric_label = METRIC_LABEL[cfg.metric]

    early = peak_df[peak_df["early_window_complete"]]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(24, 5.5))
    _plot_peak_day_panel(ax1, peak_df, dist, cfg)
    _plot_log_hist_panel(
        ax2, peak_df["peak_traffic"], color="#55A868", fit_color="#C44E52",
        title=f"峰值当天流量分布（近 {cfg.weeks} 周内发布，对数刻度）",
        xlabel=f"峰值当天{metric_label}（对数刻度）",
    )
    if not early.empty:
        _plot_log_hist_panel(
            ax3, early["early_window_traffic"], color="#8172B2", fit_color="#C44E52",
            title=f"发布后{cfg.early_window_days}天内累计流量分布（对数刻度，n={len(early)}）",
            xlabel=f"发布后{cfg.early_window_days}天累计{metric_label}（对数刻度）",
        )
    else:
        ax3.axis("off")
        ax3.set_title(f"发布后{cfg.early_window_days}天内累计流量分布")
        ax3.text(0.5, 0.5, "暂无发布满窗口天数的商品", ha="center", va="center")

    fig.tight_layout()
    fig.savefig(cfg.chart_path, dpi=150)
    plt.close(fig)


def _build_early_window_stats(peak_df: pd.DataFrame, cfg: TrafficPeakConfig) -> pd.DataFrame:
    """发布满 early_window_days 天的商品，早期累计流量的汇总统计。"""
    cols = ["指标", "数值"]
    early = peak_df[peak_df["early_window_complete"]] if not peak_df.empty else peak_df
    if early.empty:
        return pd.DataFrame(columns=cols)

    s = early["early_window_traffic"].astype(float)
    rows = [
        (f"样本商品数（发布满{cfg.early_window_days}天）", int(len(s))),
        ("流量总和", int(s.sum())),
        ("平均值", round(float(s.mean()), 1)),
        ("中位数", float(s.median())),
        ("P25", float(s.quantile(0.25))),
        ("P75", float(s.quantile(0.75))),
        ("最小值", int(s.min())),
        ("最大值", int(s.max())),
    ]
    return pd.DataFrame(rows, columns=cols)


def _build_field_doc(cfg: TrafficPeakConfig) -> pd.DataFrame:
    metric_label = METRIC_LABEL[cfg.metric]
    n = cfg.early_window_days
    rows = [
        ("按商品明细", "item_id", "淘宝商品ID（宝贝ID）"),
        ("按商品明细", "product_code", "商家编码/货号"),
        ("按商品明细", "item_name", "商品标题"),
        ("按商品明细", "brand", "品牌"),
        ("按商品明细", "publication_date", "商品发布/上架日期"),
        ("按商品明细", "days_observed", "目前有流量数据覆盖到发布后第几天（是数据进度，不代表商品已上架这么多天）"),
        ("按商品明细", "total_traffic", f"发布至今累计流量（{metric_label}）"),
        ("按商品明细", "peak_day", "流量最高的一天是发布后第几天（发布当天记为第1天）"),
        ("按商品明细", "peak_traffic", "峰值那一天的流量数值"),
        ("按商品明细", "early_window_traffic", f"发布后{n}天内的累计流量"),
        ("按商品明细", "early_window_complete",
         f"是否已发布满{n}天：True=数据完整可比较；False=还不满{n}天，early_window_traffic只是部分数据，不建议横向比较"),
        ("峰值日分布", "peak_day", "发布后第几天"),
        ("峰值日分布", "product_count", "流量峰值出现在这一天的商品数量"),
        ("峰值日分布", "pct", "占全部统计商品的百分比"),
        ("峰值日分布", "cum_pct", "累计百分比（例如“第7天累计65%”代表65%的商品在第7天或之前已经见顶）"),
        (f"发布{n}天流量统计", "样本商品数", f"已发布满{n}天、纳入统计的商品数"),
        (f"发布{n}天流量统计", "流量总和", f"这些商品{n}天内流量的总和"),
        (f"发布{n}天流量统计", "平均值", "算术平均，容易被极少数爆款拉高"),
        (f"发布{n}天流量统计", "中位数", "更能代表大多数商品的真实水平"),
        (f"发布{n}天流量统计", "P25 / P75", "25%/75%分位数，划出“较差的1/4”和“较好的1/4”的分界线"),
        (f"发布{n}天流量统计", "最小值 / 最大值", "区间边界，能看出极端值"),
    ]
    return pd.DataFrame(rows, columns=["所在Sheet", "字段", "含义"])


def _export_excel(peak_df: pd.DataFrame, dist_df: pd.DataFrame, cfg: TrafficPeakConfig) -> None:
    if not cfg.output_path:
        return
    Path(cfg.output_path).parent.mkdir(parents=True, exist_ok=True)
    early_stats_df = _build_early_window_stats(peak_df, cfg)
    field_doc_df = _build_field_doc(cfg)

    with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
        field_doc_df.to_excel(writer, index=False, sheet_name="字段说明")
        peak_df.to_excel(writer, index=False, sheet_name="按商品明细")
        dist_df.to_excel(writer, index=False, sheet_name="峰值日分布")
        early_stats_df.to_excel(writer, index=False, sheet_name=f"发布{cfg.early_window_days}天流量统计")

    if cfg.chart_path and Path(cfg.chart_path).exists():
        from openpyxl import load_workbook
        from openpyxl.drawing.image import Image as XLImage

        wb = load_workbook(cfg.output_path)
        ws = wb["峰值日分布"]
        ws.add_image(XLImage(cfg.chart_path), "F2")
        wb.save(cfg.output_path)


def analyze_traffic_peak(cfg: TrafficPeakConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    分析发布时间在近 cfg.weeks 周内的商品，找出每个商品流量（visitors/pageviews）
    达到峰值的天数（发布当天=day 1），并汇总出峰值日分布。
    """
    raw = _fetch_daily_traffic(cfg)
    peak_df = _compute_summary(raw, cfg)
    dist_df = _build_distribution(peak_df)

    _plot_charts(peak_df, dist_df, cfg)
    _export_excel(peak_df, dist_df, cfg)

    if not peak_df.empty:
        mean_day = peak_df["peak_day"].mean()
        median_day = peak_df["peak_day"].median()
        mode_day = peak_df["peak_day"].mode().iloc[0]
        print(f"✅ 分析完成：共 {len(peak_df)} 个商品（近 {cfg.weeks} 周内发布，含有效{METRIC_LABEL[cfg.metric]}）")
        print(f"   峰值日：均值={mean_day:.1f}  中位数={median_day:.0f}  众数={mode_day:.0f}")

        early = peak_df[peak_df["early_window_complete"]]
        if not early.empty:
            s = early["early_window_traffic"]
            print(f"   发布后{cfg.early_window_days}天内累计{METRIC_LABEL[cfg.metric]}"
                  f"（样本 {len(early)} 个，已发布满{cfg.early_window_days}天）：")
            print(f"     总和={int(s.sum())}  均值={s.mean():.1f}  中位数={s.median():.0f}")
        else:
            print(f"   ⚠️ 没有商品发布已满{cfg.early_window_days}天，暂无法统计早期流量")

        if cfg.output_path:
            print(f"   Excel：{cfg.output_path}")
        if cfg.chart_path:
            print(f"   分布图：{cfg.chart_path}")
    else:
        print("⚠️ 没有满足条件的商品（检查发布时间范围 / 流量数据是否已导入）")

    return peak_df, dist_df


if __name__ == "__main__":
    analyze_traffic_peak(
        TrafficPeakConfig(
            weeks=4,
            metric="visitors",
            brand=None,
            output_path=r"D:\TB\analytics\export\traffic_peak_last4w.xlsx",
            chart_path=r"D:\TB\analytics\export\traffic_peak_last4w.png",
        )
    )
