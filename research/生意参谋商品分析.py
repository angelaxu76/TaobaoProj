# -*- coding: utf-8 -*-
"""
生意参谋商品评分（代购店铺友好版）
- 稳健归一化（1%~99%裁剪 + MinMax）
- 默认弱化转化率、强调GMV/件数与“兴趣”指标（加购/收藏）
- 负向指标重点扣分：退款/退货
- 支持按“Top/Bottom百分比”或“TopN/BottomN”输出
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime

# =============== 👇 可调参数区（按需修改）================

# 输入 Excel 路径
INPUT_PATH = r"D:\TB\sycm\生意参谋商品信息\【生意参谋平台】商品_全部_2025-08-03_2025-08-09.xls"

# 输出根目录（自动创建时间戳子目录）
OUTPUT_BASE_DIR = r"D:\TB\sycm\生意参谋商品分析结果"

# 输出策略：二选一
SELECT_BY_PERCENT = True   # True=按百分比, False=按TopN/BottomN
GOOD_PCT = 0.15            # 前15%作为优品
BAD_PCT = 0.15             # 后15%作为待改进
TOP_N = 50                 # 若 SELECT_BY_PERCENT=False，则取Top_N/Bottom_N
BOTTOM_N = 50

# 列名优先匹配（可自定义覆盖；留空则用“模糊中文候选”自动识别）
# 例如：COL_OVERRIDES = {"gmv":"支付金额(元)","units":"支付件数","conv":"支付转化率"}
COL_OVERRIDES = {
    # "gmv": "",
    # "units": "",
    # "conv": "",
    # "ctr": "",
    # "cart": "",
    # "fav": "",
    # "buyers": "",
    # "uv": "",
    # "refund": "",
    # "return": "",
    # "bounce": "",
}

# 代购店铺默认权重（可按需调整）
POS_WEIGHTS = {
    "gmv":   0.50,  # 支付金额（GMV）
    "units": 0.25,  # 支付件数
    "cart":  0.15,  # 加购率/加购人数/加购件数
    "fav":   0.05,  # 收藏率/收藏人数
    "ctr":   0.05,  # 点击率（辅助）
    "conv":  0.00,  # 转化率（弱化：默认不计分）
    "buyers":0.00,  # 买家数（如要考虑可给权重）
    "uv":    0.00,  # 访客数（一般无需计分）
}
NEG_WEIGHTS = {
    "refund": 0.30,  # 退款率/退款占比
    "return": 0.20,  # 退货率
    "bounce": 0.10,  # 跳失率（如有）
}

# 评分时展示名称列（若留空则自动尝试识别）
NAME_COL_CANDIDATES = ["商品名称", "宝贝名称", "商品", "标题", "Item", "Product"]

# 结果文件名
ALL_FILE_NAME   = "全部商品_含评分.xlsx"
GOOD_FILE_NAME  = "优品TOP.xlsx"
BAD_FILE_NAME   = "待改进BOTTOM.xlsx"

# ======================================================


def robust_minmax(s: pd.Series) -> pd.Series:
    """稳健归一化：按1%~99%分位裁剪后做Min-Max。"""
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() == 0:
        return pd.Series([0.0] * len(s), index=s.index)
    q1 = s.quantile(0.01)
    q99 = s.quantile(0.99)
    s_clip = s.clip(lower=q1, upper=q99)
    mn, mx = s_clip.min(), s_clip.max()
    if pd.isna(mn) or pd.isna(mx) or mx == mn:
        return pd.Series([0.0] * len(s), index=s.index)
    return (s_clip - mn) / (mx - mn)


def find_col_auto(df: pd.DataFrame, candidates):
    """在df中按候选中文片段模糊匹配列名，匹配到即返回列名，否则None。"""
    for col in df.columns:
        name = str(col)
        for cand in candidates:
            if cand in name:
                return col
    return None


def build_column_map(df: pd.DataFrame) -> dict:
    """根据 overrides + 候选词，构建各指标对应的实际列名映射。"""

    # 中文候选（按常见“生意参谋/业务中台”表头）
    POS_MAP = {
        "gmv":   ["支付金额", "成交金额", "支付总金额", "销售额"],
        "units": ["支付件数", "成交件数", "销量"],
        "buyers":["支付买家数", "成交人数", "成交买家数"],
        "conv":  ["转化率", "支付转化率"],
        "ctr":   ["点击率"],
        "cart":  ["加购率", "加购人数", "加购件数"],
        "fav":   ["收藏人数", "收藏率"],
        "uv":    ["访客数", "浏览人数", "UV"]
    }
    NEG_MAP = {
        "refund": ["退款率", "退款笔数占比"],
        "return": ["退货率"],
        "bounce": ["跳失率"],
    }

    resolved = {}

    # 先应用用户覆盖
    for k, v in COL_OVERRIDES.items():
        if v:
            if v in df.columns:
                resolved[k] = v
            else:
                print(f"⚠️ 覆盖列 {k}='{v}' 不在数据中，忽略该覆盖。")

    # 自适应匹配未覆盖的
    for k, cands in POS_MAP.items():
        if k not in resolved:
            col = find_col_auto(df, cands)
            if col is not None:
                resolved[k] = col
    for k, cands in NEG_MAP.items():
        if k not in resolved:
            col = find_col_auto(df, cands)
            if col is not None:
                resolved[k] = col

    return resolved


def pick_name_column(df: pd.DataFrame) -> str | None:
    for cand in NAME_COL_CANDIDATES:
        if cand in df.columns:
            return cand
    # 退而求其次：找含“品”或“名”的列
    for col in df.columns:
        if ("名" in str(col)) or ("品" in str(col)):
            return col
    return None


def score_dataframe(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """根据权重与列映射生成综合评分与排名。"""
    score = pd.Series(0.0, index=df.index)

    # 正向加分
    for key, w in POS_WEIGHTS.items():
        if w == 0:
            continue
        col = col_map.get(key)
        if col is not None:
            score += w * robust_minmax(df[col])

    # 负向扣分
    for key, w in NEG_WEIGHTS.items():
        if w == 0:
            continue
        col = col_map.get(key)
        if col is not None:
            score -= w * robust_minmax(df[col])

    out = df.copy()
    out["综合评分"] = score.round(6)
    out["排名"] = out["综合评分"].rank(ascending=False, method="dense").astype(int)
    return out


def select_good_bad(df_scored: pd.DataFrame):
    """根据选择策略筛选优品/待改进集合。"""
    if SELECT_BY_PERCENT:
        p_high = df_scored["综合评分"].quantile(1 - GOOD_PCT)  # 前GOOD_PCT
        p_low = df_scored["综合评分"].quantile(BAD_PCT)       # 后BAD_PCT
        good_df = df_scored[df_scored["综合评分"] >= p_high].sort_values("综合评分", ascending=False)
        bad_df = df_scored[df_scored["综合评分"] <= p_low].sort_values("综合评分", ascending=True)
    else:
        good_df = df_scored.sort_values("综合评分", ascending=False).head(TOP_N)
        bad_df = df_scored.sort_values("综合评分", ascending=True).head(BOTTOM_N)
    return good_df, bad_df


def main():
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(f"未找到输入文件：{INPUT_PATH}")

    df = pd.read_excel(INPUT_PATH)
    # 清理全空行/列
    df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)

    # 列映射
    col_map = build_column_map(df)

    # 计算评分
    df_scored = score_dataframe(df, col_map)

    # 选择优/差
    good_df, bad_df = select_good_bad(df_scored)

    # 生成输出路径
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUTPUT_BASE_DIR, f"生意参谋_综合评分_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    all_path  = os.path.join(out_dir, ALL_FILE_NAME)
    good_path = os.path.join(out_dir, GOOD_FILE_NAME)
    bad_path  = os.path.join(out_dir, BAD_FILE_NAME)

    # 写入Excel，附带“评分配置”页
    with pd.ExcelWriter(all_path, engine="openpyxl") as w:
        df_scored.sort_values("综合评分", ascending=False).to_excel(w, index=False, sheet_name="全部(降序)")

        # 记录映射与权重
        meta_rows = []
        meta_rows.append(["正向指标", "匹配到的列名", "权重"])
        for k, wgt in POS_WEIGHTS.items():
            meta_rows.append([k, col_map.get(k), wgt])
        meta_rows.append(["负向指标", "匹配到的列名", "权重"])
        for k, wgt in NEG_WEIGHTS.items():
            meta_rows.append([k, col_map.get(k), wgt])

        pd.DataFrame(meta_rows, columns=["指标/类型", "列名", "权重"]).to_excel(w, index=False, sheet_name="评分配置")

    good_df.to_excel(good_path, index=False)
    bad_df.to_excel(bad_path, index=False)

    name_col = pick_name_column(df_scored)
    preview_cols = [c for c in [name_col, "综合评分", "排名"] if c]
    print("✅ 输出完成")
    print(f"全部：{all_path}")
    print(f"优品：{good_path}  （{len(good_df)} 行）")
    print(f"待改进：{bad_path}  （{len(bad_df)} 行）")
    if preview_cols:
        print("\n【优品预览】")
        print(good_df.sort_values("综合评分", ascending=False)[preview_cols].head(10).to_string(index=False))
        print("\n【待改进预览】")
        print(bad_df.sort_values("综合评分", ascending=True)[preview_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
