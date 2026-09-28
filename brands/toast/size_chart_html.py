# -*- coding: utf-8 -*-
"""
TOAST 尺码表 → 中文 HTML 页面（样式沿用 outdoorandcountry 的 Barbour 实测尺码表）

输入是 fetch_size_charts 保存的 {编码}_size.json：
{
  "code": ..., "name": ..., "gender": ..., "style_category": ...,
  "individual": {"header": ["Size", "Front length (CM)", ...], "rows": [["XS", "61", ...], ...]} | null,
  "group": [{"title": ..., "header": [...], "rows": [[...]], "note": ...}, ...]
}
"""
from __future__ import annotations

import html
import re
from typing import List, Optional

# 表头英文关键词 → 中文（按顺序匹配，先匹配先用；越具体的放越前面）
HEADER_MAP = [
    (r"^size$", "尺码"),
    (r"^uk$", "英码"),
    (r"^eu$", "欧码"),
    (r"^us$", "美码"),
    (r"^it$", "意码"),
    (r"^fr$", "法码"),
    (r"^jp$", "日码"),
    (r"chest\s*width|pit to pit|armpit", "胸宽(平铺)"),
    (r"\bbust\b", "胸围"),
    (r"\bchest\b", "胸围"),
    (r"waist\s*width", "腰宽(平铺)"),
    (r"\bwaist\b", "腰围"),
    (r"hip\s*width", "臀宽(平铺)"),
    (r"\bhips?\b", "臀围"),
    (r"\bshoulder", "肩宽"),
    (r"\bsleeve", "袖长"),
    (r"front\s*rise", "前裆"),
    (r"back\s*rise", "后裆"),
    (r"\brise\b", "裆深"),
    (r"inside\s*leg|inseam", "内长"),
    (r"outside\s*leg", "外长"),
    (r"\bthigh", "大腿围"),
    (r"leg\s*opening", "裤口宽"),
    (r"hem\s*width|\bhem\b", "下摆"),
    (r"\bneck|\bcollar", "领围"),
    (r"front\s*length", "前衣长"),
    (r"back\s*length", "后衣长"),
    (r"\blength\b", "长度"),
    (r"\bwidth\b", "宽度"),
    (r"\bheight\b", "身高"),
]


def translate_header(header: str) -> str:
    """英文表头 → 中文，保留括号里的单位；未识别的原样返回"""
    h = (header or "").strip()
    m = re.search(r"\(([^)]+)\)", h)
    unit = f"({m.group(1).upper()})" if m else ""
    base = re.sub(r"\([^)]*\)", "", h).strip().lower()
    for pattern, zh in HEADER_MAP:
        if re.search(pattern, base):
            return f"{zh}{unit}"
    return h


def _table_html(header: List[str], rows: List[List[str]]) -> str:
    head = "".join(f"<th>{html.escape(translate_header(h))}</th>" for h in header)
    body = "\n".join(
        "    <tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"""    <table>
    <tr>{head}</tr>
{body}
    </table>"""


def build_size_chart_html(data: dict, brand_label: str = "TOAST") -> Optional[str]:
    individual = data.get("individual")
    groups = data.get("group") or []
    if not individual and not groups:
        return None

    name = data.get("name") or data.get("code") or ""
    title = f"{brand_label} {name} 尺码表"

    sections: List[str] = []
    if individual:
        sections.append(f"""
    <h3 style="font-size:36px;">成衣实测尺寸</h3>
{_table_html(individual["header"], individual["rows"])}
    <ul>
        <li style="font-size:28px;">以上为成衣实测数据，单位：厘米；</li>
        <li style="font-size:28px;">【注】纯手工测量会存在1-2厘米误差，具体以实物为准。</li>
    </ul>""")

    for g in groups:
        sections.append(f"""
    <h3 style="font-size:36px;">尺码对照 · 参考身体尺寸</h3>
{_table_html(g["header"], g["rows"])}
    <ul>
        <li style="font-size:28px;">此表为品牌设计时参考的<strong>人体净尺寸</strong>，并非衣服本身的尺寸；</li>
        <li style="font-size:28px;">请按自己的胸围/腰围/臀围对照选码，介于两码之间建议选大一码。</li>
    </ul>""")

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>

<style>
    body {{
        background-color: #f3f4f2;
        font-family: Arial, sans-serif;
        text-align: center;
        margin: 0;
        padding: 0;
    }}

    .container {{
        max-width: 800px;
        margin: 20px auto;
        background-color: #ffffff;
        padding: 30px;
        border-radius: 14px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
        border: 1.5px solid #e2e2e2;
        text-align: left;
    }}

    h2 {{
        color: #ffffff;
        background-color: #3d3a35;
        text-align: center;
        font-size: 48px;
        padding: 20px;
        border-radius: 12px 12px 0 0;
        letter-spacing: 1px;
    }}

    h3 {{
        font-size: 33px;
        font-weight: bold;
        border-left: 6px solid #3d3a35;
        padding-left: 15px;
        margin-top: 28px;
        color: #2c2c2c;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 14px;
        border: 1.5px solid #e5e5e5;
        border-radius: 10px;
        overflow: hidden;
    }}

    th {{
        background-color: #5a5650;
        color: #ffffff;
        border: 1px solid #d9d9d9;
        padding: 12px 6px;
        text-align: center;
        font-size: 24px;
        font-weight: bold;
    }}

    td {{
        border: 1px solid #e6e6e6;
        padding: 12px 6px;
        text-align: center;
        font-size: 26px;
        color: #333333;
    }}

    tr:nth-child(even) td {{
        background-color: #f7f7f7;
    }}

    tr:nth-child(odd) td {{
        background-color: #ffffff;
    }}

    li {{
        color: #3a3a3a;
        line-height: 1.7;
    }}

    strong {{
        font-weight: bold;
        color: #8B0000;
    }}
</style>

</head>
<body>

<div class="container">

    <h2 style="font-size:50px;">{html.escape(title)}</h2>
{"".join(sections)}
</div>

</body>
</html>
"""
