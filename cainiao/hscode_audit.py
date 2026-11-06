# -*- coding: utf-8 -*-
"""
海关备案结果核对：订单里的每个货品要么进了备案 Excel，要么进异常清单，不允许悄悄丢失。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd


def hscode_issue(goods_id: str, brand: str, stage: str, reason: str) -> dict:
    return {"货品ID": goods_id, "品牌": brand, "环节": stage, "原因": reason}


def report_hscode_audit(output_dir, order_ids, generated_ids, issues, ignored_files=()) -> Path | None:
    """
    打印核对汇总；有未生成货品时输出异常清单 Excel 并返回其路径。

    order_ids:     订单中全部货品ID（用于兜底发现既没生成、也没记录原因的货品）
    generated_ids: 实际写入备案 Excel 的货品ID
    issues:        hscode_issue() 组成的列表
    ignored_files: 因缺少货品列而未处理的文件名（Downloads 里常有无关 Excel，只提醒不算异常）
    """
    generated = {str(i) for i in generated_ids}

    # 同一货品可能在订单里出现多次，这里按货品ID去重；没有ID的行逐条保留
    unique_issues, seen = [], set()
    for item in issues:
        goods_id = item["货品ID"]
        if goods_id and (goods_id in generated or goods_id in seen):
            continue
        seen.add(goods_id)
        unique_issues.append(item)

    for goods_id in sorted({str(i) for i in order_ids} - generated - seen):
        unique_issues.append(hscode_issue(goods_id, "", "核对", "订单里有，但未生成（原因未知）"))

    # 异常清单先落盘，再打印
    audit_path = None
    if unique_issues:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_path = output_dir / f"备案异常清单_{ts}.xlsx"
        pd.DataFrame(unique_issues).to_excel(audit_path, index=False)

    generated_count, issue_count = len(generated), len(unique_issues)
    print("\n" + "=" * 60)
    print(f"备案核对：订单货品 {generated_count + issue_count} 个 / "
          f"已生成 {generated_count} 个 / 未生成 {issue_count} 个")

    if ignored_files:
        print(f"⚠ 以下文件缺少货品列，未处理（如果是订单文件请检查）：{list(ignored_files)}")

    if unique_issues:
        for item in unique_issues:
            print(f"  - 货品ID={item['货品ID'] or '(空)'} [{item['品牌'] or '未知品牌'}] "
                  f"{item['环节']}：{item['原因']}")
        print(f"❌ 有 {issue_count} 个货品未生成备案，处理后需重新生成：{audit_path}")
    elif generated_count == 0:
        print("⚠ 没有解析到任何货品，请检查订单文件")
    else:
        print("✅ 全部货品已生成备案")
    print("=" * 60)

    return audit_path
