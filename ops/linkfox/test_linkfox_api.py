"""
LinkFox API 连通性测试脚本。

直接运行即可，无需 Excel 或品牌配置：
    python ops/linkfox/test_linkfox_api.py

测试内容：
  1. 提交换模特任务（submit）
  2. 轮询任务结果（poll_result）—— status=3 成功，返回 resultList[].url
  3. 下载结果图到本地
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root

import requests
from common.ai.image.linkfox_client import LinkFoxClient
from config import LINKFOX_API_KEY, LINKFOX_HOST

# ============================================================
# 测试参数（按需替换为真实图片 URL）
# ============================================================

# 原始模特拍摄图（含服装，AI 保留服装结构）
TEST_IMAGE_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/product_front/LCA0362WH11_front_1.jpg"

# 目标模特头部参考图
TEST_MODEL_IMAGE_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.png"

# 结果图本地保存路径
OUTPUT_PATH = os.path.join(_HERE, "test_output.jpg")

# ============================================================


def main():
    print("=" * 60)
    print("LinkFox API 连通性测试")
    print("=" * 60)
    print(f"API Host  : {LINKFOX_HOST}")
    print(f"API Key   : {LINKFOX_API_KEY[:8]}...（已隐藏）")
    print(f"原始模特图: {TEST_IMAGE_URL}")
    print(f"目标模特图: {TEST_MODEL_IMAGE_URL}")
    print()

    client = LinkFoxClient(api_key=LINKFOX_API_KEY, host=LINKFOX_HOST)

    # ── Step 1: 提交任务 ─────────────────────────────────────
    print("Step 1: 提交换模特任务 ...")
    task_id = client.submit(
        image_url=TEST_IMAGE_URL,
        model_image_url=TEST_MODEL_IMAGE_URL,
        real_model=True,
        output_num=1,
    )

    if not task_id:
        print("\n[FAIL] 任务提交失败，请检查 API Key 和图片 URL。")
        return

    print(f"[OK] 任务已提交，task_id = {task_id}")

    # ── Step 2: 轮询结果 ─────────────────────────────────────
    print("\nStep 2: 轮询任务结果（最长等待 300s）...")
    result_urls = client.poll_result(task_id, interval=5, max_wait=300)

    if not result_urls:
        print("\n[FAIL] 未获取到结果图。")
        return

    print(f"[OK] 获取到 {len(result_urls)} 张结果图")
    for i, url in enumerate(result_urls, 1):
        print(f"  [{i}] {url}")

    # ── Step 3: 下载结果图 ───────────────────────────────────
    print(f"\nStep 3: 下载结果图 → {OUTPUT_PATH}")
    try:
        img_data = requests.get(result_urls[0], timeout=60).content
        with open(OUTPUT_PATH, "wb") as f:
            f.write(img_data)
        size_kb = len(img_data) // 1024
        print(f"[OK] 下载成功，文件大小: {size_kb} KB")
    except Exception as e:
        print(f"[FAIL] 下载失败: {e}")
        return

    print()
    print("=" * 60)
    print("测试通过！结果图已保存：", OUTPUT_PATH)
    print("=" * 60)


if __name__ == "__main__":
    main()
