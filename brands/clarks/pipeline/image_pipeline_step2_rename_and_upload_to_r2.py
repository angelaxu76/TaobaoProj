"""
Clarks 商品图流水线 — step 2：按新顺序重命名 + 上传到 R2。

前置条件：image_pipeline_step1_download.py 下载完图片后，你已经在
CLARKS["IMAGE_DOWNLOAD"] 里手动删掉了不需要的模特图/生活场景图。

重命名规则（brands/clarks/helpers_local/rename_suffix.py）：原来的
1,6,2,3,5,4,7,8,9 依次改成 1,2,3,4,5,6,7,8,9（6->2, 2->3, 3->4, 4->6，
1/5/7/8/9 位置不变），原地改在 IMAGE_DOWNLOAD 里。

改完名之后，按 CODE_FILE_PATH 里的编码过滤，把 IMAGE_DOWNLOAD 传到 R2
（"clarks/" 前缀，文件名不变），供 image_pipeline_step2_ai_rotate.py 用。

R2 账号/桶配置跟 ops/r2_upload/upload_images_to_r2.py 保持一致（同一个
Cloudflare 账号下的 product-assets 桶），Access Key 通过环境变量
R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY 传入（设置后需重开终端）。
"""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from brands.clarks.helpers_local.rename_suffix import rename_reordered_suffix
from common.ai.image.s3_utils import upload_local_file_to_r2
from config import CLARKS, R2_PUBLIC_PREFIX

R2_ACCOUNT_ID = "af51016d1487afef5637f23021b4afae"
R2_BUCKET_NAME = "product-assets"

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")

R2_PATH_PREFIX = "clarks/"
CODE_FILE_PATH = r"D:\TB\Products\clarks\repulibcation\publication_codes.txt"
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

    image_dir = Path(CLARKS["IMAGE_DOWNLOAD"])

    print("按新顺序重命名（1,6,2,3,5,4,7,8,9 -> 1,2,3,4,5,6,7,8,9）")
    rename_reordered_suffix(image_dir)

    files = sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.stem.split("_")[0] in codes
    )
    if not files:
        print(f"[提示] {image_dir} 下没有找到本批编码对应的图片，请先跑 image_pipeline_step1_download.py")
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
