# enrich_tax_excel_from_db.py
import argparse
import os
import re
from typing import List, Optional, Dict, Any

from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

from cfg.db_config import PGSQL_CONFIG


TABLE_NAME = "taobao_order_logistics"

# 可能的“订单号”列名候选（税务推送Excel里经常会不同）
ORDER_ID_COL_CANDIDATES = [
    "订单编号",
    "订单号",
    "淘宝订单号",
    "主订单号",
    "交易订单号",
    "订单ID",
    "Order ID",
]

DB_CONFIG = PGSQL_CONFIG   # ✅ 关键行
def get_engine():
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    return create_engine(url)

def normalize_order_id(x) -> Optional[str]:
    """统一订单号：去空格、去末尾 .0（Excel常见）、保持字符串"""
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = re.sub(r"\.0$", "", s)
    s = re.sub(r"\s+", "", s)
    return s if s else None


def detect_order_id_col(df: pd.DataFrame) -> str:
    for c in ORDER_ID_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise KeyError(
        f"未找到订单号列。候选列名：{ORDER_ID_COL_CANDIDATES}\n"
        f"当前Excel列名：{list(df.columns)}"
    )


# 可能的“退款单号”列名候选
REFUND_ID_COL_CANDIDATES = ["退款单号", "退款编号", "退货单号"]


def detect_refund_col(df: pd.DataFrame) -> Optional[str]:
    for c in REFUND_ID_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def is_return_order(val) -> bool:
    """判断退款单号是否表示该订单为退货订单"""
    if val is None:
        return False
    if isinstance(val, float) and pd.isna(val):
        return False
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "0", "0.0"):
        return False
    return True


def is_blank(val) -> bool:
    """判断字段是否为空（None/NaN/空字符串）"""
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    s = str(val).strip()
    return not s or s.lower() in ("nan", "none")


def chunk_list(items: List[str], size: int = 1000) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# 价格相关栏目关键词：命中即视为金额列，导出时转为数字类型
MONEY_COL_KEYWORDS = ["金额", "费", "价格", "佣金", "打款", "货款"]


def parse_money(val) -> Optional[float]:
    """金额统一转 float（支持¥、逗号、空、None/NaN）"""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("¥", "").replace(",", "").replace("，", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def convert_money_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将所有名称含金额相关关键词的列转为数字类型"""
    for col in df.columns:
        if any(kw in col for kw in MONEY_COL_KEYWORDS):
            df[col] = df[col].apply(parse_money)
    return df


def fetch_order_info(engine, order_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    从 taobao_order_logistics 批量取数。
    返回 dict: {order_id: {sales_mode, jingya_profit, total_amount, tracking_no, logistics_company, merchant_note}}
    """
    if not order_ids:
        return {}

    result_map: Dict[str, Dict[str, Any]] = {}

    sql = text(f"""
        SELECT
            order_id,
            sales_mode,
            jingya_profit,
            total_amount,
            tracking_no,
            logistics_company,
            merchant_note
        FROM {TABLE_NAME}
        WHERE order_id = ANY(:order_ids)
    """)

    with engine.begin() as conn:
        # 分批查询，避免参数过大
        for batch in chunk_list(order_ids, 3000):
            rows = conn.execute(sql, {"order_ids": batch}).mappings().all()
            for r in rows:
                oid = r["order_id"]
                result_map[str(oid)] = {
                    "sales_mode": r.get("sales_mode"),
                    "jingya_profit": r.get("jingya_profit"),
                    "total_amount": r.get("total_amount"),
                    "tracking_no": r.get("tracking_no"),
                    "logistics_company": r.get("logistics_company"),
                    "merchant_note": r.get("merchant_note"),
                }

    return result_map


def enrich_excel(input_path: str, output_path: Optional[str] = None) -> str:
    input_file = Path(input_path)
    if input_file.suffix.lower() == ".csv":
        df = pd.read_csv(input_file, dtype=str, encoding="gb18030")
    else:
        df = pd.read_excel(input_file, dtype=str)

    order_col = detect_order_id_col(df)
    df["_order_id_norm"] = df[order_col].apply(normalize_order_id)

    refund_col = detect_refund_col(df)
    if refund_col:
        df["_is_return"] = df[refund_col].apply(is_return_order)
    else:
        df["_is_return"] = False

    order_ids = (
        df["_order_id_norm"]
        .dropna()
        .unique()
        .tolist()
    )

    engine = get_engine()
    order_info_map = fetch_order_info(engine, order_ids)

    # 新增列（先空着）
    df["经营模式"] = ""
    df["真实金额"] = ""
    df["tracking_no"] = ""
    df["logistics_company"] = ""
    df["_merchant_note"] = ""

    # 回填
    not_found = 0
    for idx, oid in df["_order_id_norm"].items():
        if not oid:
            continue

        info = order_info_map.get(oid)
        if not info:
            not_found += 1
            # 找不到就默认海外直邮（你也可以改成留空）
            df.at[idx, "经营模式"] = "海外直邮"
            continue

        sales_mode_db = (info.get("sales_mode") or "").strip()
        is_distribution = (sales_mode_db == "分销")

        df.at[idx, "经营模式"] = "鲸芽分销" if is_distribution else "海外直邮"

        # 真实金额：分销取利润，普通取总额
        real_amount = info.get("jingya_profit") if is_distribution else info.get("total_amount")

        # 转字符串写入（避免科学计数法/空值）
        df.at[idx, "真实金额"] = "" if real_amount is None else str(real_amount)

        # tracking / company
        df.at[idx, "tracking_no"] = "" if info.get("tracking_no") is None else str(info.get("tracking_no"))
        df.at[idx, "logistics_company"] = "" if info.get("logistics_company") is None else str(info.get("logistics_company"))
        df.at[idx, "_merchant_note"] = "" if info.get("merchant_note") is None else str(info.get("merchant_note"))

    # 输出路径默认：原文件名 + _enriched.xlsx
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_enriched{ext if ext else '.xlsx'}"

    # 清理内部列
    df.drop(columns=["_order_id_norm"], inplace=True)

    # 按经营模式拆分为两个 sheet：鲸芽分销 / 海外直邮
    df_jingya = df[df["经营模式"] == "鲸芽分销"].copy()
    df_overseas = df[df["经营模式"] == "海外直邮"].copy()

    # 鲸芽分销 sheet 不需要商家备注列，去掉临时列
    df_jingya.drop(columns=["_merchant_note"], inplace=True)
    # 分销订单的“真实金额”实为运营服务费，改名
    df_jingya.rename(columns={"真实金额": "运营服务费"}, inplace=True)

    # 海外直邮 sheet：四列人工填写列（先留空）+ 商家备注（从数据库取值）
    df_overseas.rename(columns={"_merchant_note": "商家备注", "真实金额": "海外直邮订单毛利"}, inplace=True)
    for col in ["海外采购供货商名称", "海外采购订单号", "海外采购金额外币", "货币", "海外采购金额换算人民币"]:
        df_overseas[col] = ""
    # 海外直邮订单毛利：人工填写，先留空
    df_overseas["海外直邮订单毛利"] = ""
    # 列顺序：...海外采购金额外币 -> 货币 -> 海外采购金额换算人民币 -> 海外直邮订单毛利 -> 商家备注（最后一栏）
    reordered_cols = [c for c in df_overseas.columns if c not in ("海外直邮订单毛利", "商家备注", "货币")]
    insert_currency_at = reordered_cols.index("海外采购金额外币") + 1
    reordered_cols[insert_currency_at:insert_currency_at] = ["货币"]
    insert_at = reordered_cols.index("海外采购金额换算人民币") + 1
    reordered_cols[insert_at:insert_at] = ["海外直邮订单毛利"]
    reordered_cols.append("商家备注")
    df_overseas = df_overseas[reordered_cols]

    # 按“退款单号”拆分出退货订单，分别转移到独立 sheet
    df_jingya_return = df_jingya[df_jingya["_is_return"]].copy()
    df_jingya = df_jingya[~df_jingya["_is_return"]].copy()
    df_overseas_return = df_overseas[df_overseas["_is_return"]].copy()
    df_overseas = df_overseas[~df_overseas["_is_return"]].copy()

    for d in (df_jingya, df_jingya_return, df_overseas, df_overseas_return):
        d.drop(columns=["_is_return"], inplace=True)

    # 海外直邮订单中没有 tracking_no 的，转移到“售后费用分摊及其他收入” sheet
    no_tracking_mask = df_overseas["tracking_no"].apply(is_blank)
    df_overseas_no_tracking = df_overseas[no_tracking_mask].copy()
    df_overseas = df_overseas[~no_tracking_mask].copy()

    # 价格相关栏目统一转为数字类型，无需手动转换
    df_jingya = convert_money_columns(df_jingya)
    df_jingya_return = convert_money_columns(df_jingya_return)
    df_overseas = convert_money_columns(df_overseas)
    df_overseas_return = convert_money_columns(df_overseas_return)
    df_overseas_no_tracking = convert_money_columns(df_overseas_no_tracking)

    with pd.ExcelWriter(output_path) as writer:
        df_jingya.to_excel(writer, sheet_name="鲸芽分销", index=False)
        df_jingya_return.to_excel(writer, sheet_name="鲸芽订单-退货", index=False)
        df_overseas.to_excel(writer, sheet_name="海外直邮", index=False)
        df_overseas_return.to_excel(writer, sheet_name="海外直邮-退货", index=False)
        df_overseas_no_tracking.to_excel(writer, sheet_name="售后费用分摊及其他收入", index=False)

    print(f"✅ 输入文件: {input_path}")
    print(f"✅ 输出文件: {output_path}")
    print(f"ℹ️ 订单号列: {order_col}")
    print(f"ℹ️ 退款单号列: {refund_col or '未找到，全部按非退货处理'}")
    print(f"ℹ️ 订单数(去重): {len(order_ids)}，未在DB匹配到的行数: {not_found}")
    print(
        f"ℹ️ 鲸芽分销: {len(df_jingya)} 行, 鲸芽订单-退货: {len(df_jingya_return)} 行, "
        f"海外直邮: {len(df_overseas)} 行, 海外直邮-退货: {len(df_overseas_return)} 行, "
        f"售后费用分摊及其他收入: {len(df_overseas_no_tracking)} 行"
    )

    return output_path


def main():
    enrich_excel(r"D:\OneDrive\Documentation\淘宝会计统计数据\英国伦敦代购\202512.xlsx", r"D:\OneDrive\Documentation\淘宝会计统计数据\英国伦敦代购\202512_enrich.xlsx")


if __name__ == "__main__":
    main()
