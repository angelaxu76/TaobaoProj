from helper.HtmlToPGNBatch import process_html_folder
from helper.cutterAllsiderSpace import trim_sides_batch
from text_watermark import text_watermark_batch



def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(CAMPER)

    HTML_FOLDER = "D:/TB/HTMLToImage/input"  # HTML 文件夹路径
    OUTPUT_FOLDER = "D:/TB/HTMLToImage/output"  # 输出图片文件夹
    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径


    process_html_folder(HTML_FOLDER, OUTPUT_FOLDER, GECKODRIVER_PATH)

    result = trim_sides_batch(
        input_dir=r"D:\TB\HTMLToImage\output",
        output_dir=r"D:\TB\HTMLToImage\cutter",
        pattern="*.jpg;*.png",  # 可不传
        tolerance=5,
        recursive=False,
        overwrite=True,
        dry_run=False,
        workers=0,  # 0=自动
    )

    # 方案1：自动角标（推荐做主图）
    text_watermark_batch(
        input_dir=r"D:\TB\HTMLToImage\output",
        output_dir=r"D:\TB\HTMLToImage\watermarked",
        mode="auto-corner",
        text="英国哈梅尔百货",
        opacity=0.16,  # 0.12~0.20 比较温和
        scale=0.16,  # 文本尺寸随图自适应
        margin_ratio=0.03,
        font_path=r"C:\Windows\Fonts\msyh.ttc",
        overwrite=True,
    )


if __name__ == "__main__":
    main()
