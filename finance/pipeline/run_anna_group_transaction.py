import os
import datetime as dt
from pathlib import Path

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from finance.ingest.group_anna_records_by_retrieval_ref import group_pdfs_by_retrieval_ref


def group_pdfs_by_retrieval_ref_pipeline():
    # 示例：本月

    input_dir = Path(r"D:\OneDrive\CrossBorderDocs_UK\07_ANNA\clarks\raw")
    output_dir = Path(r"D:\OneDrive\CrossBorderDocs_UK\07_ANNA\clarks\grouped")

    group_pdfs_by_retrieval_ref(
        input_dir=input_dir,
        output_dir=output_dir,
        dry_run=False    # True = 试跑，不写文件
    )



if __name__ == "__main__":
    group_pdfs_by_retrieval_ref_pipeline()
