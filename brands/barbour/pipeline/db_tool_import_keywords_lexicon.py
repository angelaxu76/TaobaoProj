"""
keyword_lexicon 词库初始化工具

使用前：
  1. 准备 titles.txt（每行一个商品标题，可从 barbour_products 导出）
  2. 准备 keywords_style_only.txt（每行一个 L1 风格词，需人工确认）
  3. 修改下方 TITLES_PATH 和 L1_FILE 路径后运行

运行：
  python -m brands.barbour.pipeline.tool_import_keywords_lexicon
"""

from brands.barbour.core.import_keywords_lexicon import import_lexicon_from_titles

# ===== 修改这里的路径 =====
TITLES_PATH = r"D:\Projects\VS-TaobaoProj\data\barbour\titles.txt"
L1_FILE     = r"D:\Projects\VS-TaobaoProj\data\barbour\keywords_style_only.txt"
BRAND       = "barbour"
# ==========================


def run_import_keywords_lexicon():
    result = import_lexicon_from_titles(
        titles_path=TITLES_PATH,
        l1_file=L1_FILE,
        brand=BRAND,
    )
    print(f"\n完成：brand={result['brand']}，L1={result['l1_count']}，L2={result['l2_count']}")


if __name__ == "__main__":
    run_import_keywords_lexicon()
