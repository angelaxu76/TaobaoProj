"""
生成淘宝主图视频（1:1、默认 15 秒），图片来自各品牌 IMAGE_PROCESS 目录（如 D:\\TB\\Products\\ecco\\publication\\image_process）。

画面：每张图缓慢推近/拉远，交叉淡化；字幕依次为 短标题 → 卖点1 → 卖点2 → 推荐理由（同文案脚本）。
输出：{OUTPUT_DIR}\\{品牌}\\{商品编码}.mp4，以及 视频清单_*.xlsx（含渠道产品ID、各店淘宝商品ID，方便上传对应）。
运行：python -m ops.creative.run_generate_video
"""
from pathlib import Path

from creative.copywriting.copy_excel import read_copy_excel
from creative.video.service import make_videos, style_with
from ops.creative.run_generate_copy_excel import read_codes

# ==== 参数 ====
BRANDS = ["ecco"]
CODES_EXCEL: Path | None = None        # 只做 Excel 里的商品（列：商品编码 或 渠道产品ID）；None = 图片目录里的全部商品
REUSE_EXCEL: Path | None = None        # 审核修改过的 商品文案_*.xlsx：字幕直接用里面的文案
COPY_MODE = "safe"                     # 没有 REUSE_EXCEL 时现场生成文案：safe = 保守（推荐）；ai = AI 撰写
DURATION = 15                          # 秒，淘宝建议 30 秒以内
MUSIC: str | None = None               # 背景音乐文件路径（请用有版权的音乐）；None = 静音
LIMIT: int | None = None               # 每个品牌最多做几个，试跑填 3
WORKERS = 8                            # 同时渲染几个（本机 32 核；每个约占 1~2 核）
OVERWRITE = False                      # True = 已有视频也重做（改了文案/时长后用）
STORES: list[str] | None = None        # 清单里列哪些店的淘宝商品ID；None = 全部启用的店铺
OUTPUT_DIR = Path(r"D:\TB\Products\creative\video")
# ==============

if __name__ == "__main__":
    make_videos(
        BRANDS, OUTPUT_DIR,
        codes=read_codes(CODES_EXCEL) if CODES_EXCEL else None,
        style=style_with(duration=DURATION, music=MUSIC),
        copy_mode=COPY_MODE,
        reuse=read_copy_excel(REUSE_EXCEL) if REUSE_EXCEL else None,
        limit=LIMIT, workers=WORKERS, overwrite=OVERWRITE, stores=STORES,
    )
