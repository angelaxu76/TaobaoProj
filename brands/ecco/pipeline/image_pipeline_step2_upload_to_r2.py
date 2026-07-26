"""
ECCO 商品图流水线 — step 2 前半步：把裁剪好的图上传到 R2。

跟 image_pipeline_step2_ai_rotate.py 分成两个独立脚本，是因为图片经过
最大化裁剪 + 改编号后缀后，通常需要人工看一眼有没有裁错/缺图，确认没问题
再传 R2，不想跟 step1 或 AI 旋转自动连着跑。

上传目录固定读 ECCO["IMAGE_CUTTER"]（跟 step1 的输出、AI 旋转要读的目录
是同一个），只挑 CODE_FILE_PATH 里列的商品编码对应的图，上传后文件名不变，
key 前缀 "ecco/"，跟 image_pipeline_step2_ai_rotate.py 里的 R2_SHOT_SUBDIR
保持一致。

R2 账号/桶配置跟 ops/r2_upload/upload_images_to_r2.py 保持一致（同一个
Cloudflare 账号下的 product-assets 桶），Access Key 通过环境变量
R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY 传入（设置后需重开终端）。
"""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from common.ai.image.s3_utils import upload_local_file_to_r2
from config import ECCO, R2_PUBLIC_PREFIX

R2_ACCOUNT_ID = "af51016d1487afef5637f23021b4afae"
R2_BUCKET_NAME = "product-assets"

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")

R2_PATH_PREFIX = "ecco/"
CODE_FILE_PATH = r"D:\TB\Products\ecco\repulibcation\publication_codes.txt"
CONCURRENCY = 8


def _codes_from_file(path: str) -> set[str]:
    return {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}


def upload_one(file_path: Path) -> dict:
    object_key = f"{R2_PATH_PREFIX}{file_path.name}"
    ok = upload_local_file_to_r2(
        local_path=str(file_path),
        object_key=object_key,
        account_id=R2_ACCOUNT_ID,
        access_key_id=R2_ACCESS_KEY_ID,
        secret_access_key=R2_SECRET_ACCESS_KEY,
        bucket_name=R2_BUCKET_NAME,
    )
    return {"filename": file_path.name, "status": "success" if ok else "failed"}


def main():
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print("[错误] 未读取到 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY 环境变量，请先设置后重开终端")
        return

    codes = _codes_from_file(CODE_FILE_PATH)
    if not codes:
        print(f"[提示] {CODE_FILE_PATH} 未读取到任何商品编码")
        return

    image_dir = Path(ECCO["IMAGE_CUTTER"])
    files = sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.stem.split("_")[0] in codes
    )
    if not files:
        print(f"[提示] {image_dir} 下没有找到本批编码对应的图片，请先跑 image_pipeline_step1_download_and_cut.py")
        return

    print(f"[开始] 共 {len(files)} 张图片上传到 R2（{R2_BUCKET_NAME}/{R2_PATH_PREFIX}），并发 {CONCURRENCY}")

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(upload_one, p): p for p in files}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = "OK" if result["status"] == "success" else "FAIL"
            print(f"[{i}/{len(files)}] {status}  {result['filename']}")

    ok_count = sum(1 for r in results if r["status"] == "success")
    print(f"[完成] 成功 {ok_count} / 失败 {len(results) - ok_count}")
    print(f"[提示] 上传前缀 {R2_PUBLIC_PREFIX}/{R2_PATH_PREFIX} 供 image_pipeline_step2_ai_rotate.py 使用")


if __name__ == "__main__":
    main()
