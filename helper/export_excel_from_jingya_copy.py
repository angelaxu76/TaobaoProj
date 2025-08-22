import pandas as pd
from pathlib import Path

INPUT_TXT = r"D:\temp\channel_products.txt"
OUTPUT_XLSX = r"D:\temp\channel_products.xlsx"

COLUMNS = [
    "渠道产品名称", "渠道产品ID", "货品ID", "类目", "供应商名称",
    "宝贝关联状态", "价格(元)", "库存", "库存类型", "操作"
]


def parse_txt_to_excel(input_txt, output_xlsx):
    text = Path(input_txt).read_text(encoding="utf-8", errors="ignore")
    # 统一换行 & 去掉 BOM/末尾空白
    lines = [ln.strip("\ufeff").strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # 去掉空行（如果你的文件没有空行，可删除这句）
    lines = [ln for ln in lines if ln != ""]

    rows = []
    bad_blocks = []
    for i in range(0, len(lines), 10):
        block = lines[i:i + 10]
        if len(block) < 10:
            bad_blocks.append((i, block))
            break
        name, channel_id, sku_id, cat, supplier, bind_state, price, stock, stock_type, op = block

        # 轻量校验 & 清洗
        channel_id = channel_id.strip()
        sku_id = sku_id.strip()
        price = price.replace(",", "").strip()  # 遇到 1,299.00 也能处理
        stock = stock.strip()

        rows.append([
            name,
            channel_id,
            sku_id,
            cat,
            supplier,
            bind_state,
            price,
            stock,
            stock_type,
            op
        ])

    df = pd.DataFrame(rows, columns=COLUMNS)
    # 建议明确引擎，避免某些环境下引擎探测卡顿
    df.to_excel(output_xlsx, index=False, engine="openpyxl")
    print(f"✅ 已导出 Excel: {output_xlsx} | 共 {len(df)} 条记录")

    if bad_blocks:
        print("⚠️ 发现不完整的记录块（行号从0算起），请检查源TXT：")
        for idx, blk in bad_blocks[:5]:
            print(f"  - 起始行 {idx}：仅 {len(blk)} 行 -> {blk}")


if __name__ == "__main__":
    parse_txt_to_excel(INPUT_TXT, OUTPUT_XLSX)
