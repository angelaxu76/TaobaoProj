"""
LinkFox API 连通性测试脚本（curl 版）。

跟 test_linkfox_api.py 功能一致，唯一区别：HTTP 请求全部通过系统 curl.exe
（subprocess 调用）发出，不走 Python requests 库。用于对照排查
"是否是 requests 库本身导致 data.code=500 ERR_UNKNOWN" 这个疑点。

已知结论（2026-08-22 排查）：经过 curl 和 requests 的 A/B 对照测试，
两者在同一时间窗口内成功率完全一致，说明请求方式不是 500 的成因，
真正原因是 LinkFox 后端本身间歇性抖动。此脚本仅作为留存的诊断工具，
方便以后怀疑客户端差异时快速复测。

直接运行即可，无需 Excel 或品牌配置：
    python ops/linkfox/test_linkfox_api_curl.py
"""
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/linkfox/

from _session_config import LINKFOX_API_KEY, LINKFOX_HOST

SUBMIT_PATH = "/linkfox-ai/image/v2/make/changeModelFixed"
RESULT_PATH = "/linkfox-ai/image/v2/make/info"

# ============================================================
# 测试参数（按需替换为真实图片 URL）
# ============================================================

TEST_IMAGE_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/product_front/LQU0087BK91_front_1.jpg"
TEST_MODEL_IMAGE_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.png"

OUTPUT_PATH = os.path.join(_HERE, "test_output_curl.jpg")

# 单次测试重复次数（用于观察成功率/抖动规律）
REPEAT = 5

# ============================================================


def curl_post_json(url: str, payload: dict, timeout: int = 30) -> dict | None:
    """用系统 curl.exe 发一个 POST JSON 请求，返回解析后的响应体。"""
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-H", f"Authorization: Bearer {LINKFOX_API_KEY}",
        "-H", "Content-Type: application/json",
        "--data-raw", json.dumps(payload, ensure_ascii=False),
        "--max-time", str(timeout),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        print("[curl] 请求超时")
        return None

    if proc.returncode != 0:
        print(f"[curl] 退出码 {proc.returncode}，stderr: {proc.stderr.strip()[:300]}")
        return None

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"[curl] 响应不是合法 JSON: {proc.stdout[:300]}")
        return None


def submit(image_url: str, model_image_url: str) -> str | None:
    """提交换模特任务，返回任务 ID（成功）或 None（失败）。"""
    payload = {"imageUrl": image_url, "modelImageUrl": model_image_url}
    body = curl_post_json(f"{LINKFOX_HOST}{SUBMIT_PATH}", payload)
    if body is None:
        return None

    code = str(body.get("code", ""))
    if code != "0":
        print(f"[curl] 提交失败 (code={code}): {body.get('sub_msg') or body.get('msg')}")
        return None

    outer_data = body.get("data") or {}
    inner_data = outer_data.get("data") or outer_data
    task_id = inner_data.get("id")
    if not task_id:
        print(f"[curl] 提交成功但未返回 task_id，完整响应: {body}")
        return None

    print(f"[curl] 任务已提交，ID: {task_id}")
    return str(task_id)


def poll_result(task_id: str, interval: int = 5, max_wait: int = 300) -> list[str]:
    """轮询任务直到完成，返回结果图片 URL 列表。"""
    elapsed = 0
    print(f"[curl] 轮询任务结果，ID: {task_id} ...")

    while elapsed < max_wait:
        body = curl_post_json(f"{LINKFOX_HOST}{RESULT_PATH}", {"id": task_id}, timeout=15)
        if body:
            outer_code = str(body.get("code", ""))
            outer_data = body.get("data") or {}
            inner_data = outer_data.get("data") or outer_data

            if outer_code == "0":
                status = inner_data.get("status")
                if status == 3:
                    result_list = inner_data.get("resultList") or []
                    urls = [item["url"] for item in result_list
                            if item.get("status") == 1 and item.get("url")]
                    if urls:
                        print(f"[curl] 生成成功，共 {len(urls)} 张: {urls}")
                        return urls
                    print(f"[curl] status=3 但结果 URL 为空，原始 data: {inner_data}")
                    return []
                elif status == 4:
                    print(f"[curl] 任务失败 (id={task_id}): {inner_data.get('errorMsg') or '未知原因'}")
                    return []
                else:
                    label = {1: "排队中", 2: "生成中"}.get(status, f"status={status}")
                    print(f"[curl] {label}，已等待 {elapsed}s ...")
            else:
                print(f"[curl] 查询返回异常 (code={outer_code}): {body}")

        time.sleep(interval)
        elapsed += interval

    print(f"[curl] 超时（{max_wait}s），任务 {task_id} 未完成")
    return []


def download(url: str, out_path: str) -> bool:
    cmd = ["curl", "-s", "-o", out_path, url]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    return proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


def main():
    print("=" * 60)
    print("LinkFox API 连通性测试（curl 版）")
    print("=" * 60)
    print(f"API Host  : {LINKFOX_HOST}")
    print(f"API Key   : {LINKFOX_API_KEY[:8]}...（已隐藏）")
    print(f"原始模特图: {TEST_IMAGE_URL}")
    print(f"目标模特图: {TEST_MODEL_IMAGE_URL}")
    print(f"重复次数  : {REPEAT}")
    print()

    ok_count = 0
    for i in range(1, REPEAT + 1):
        print(f"\n{'-' * 60}\n第 {i}/{REPEAT} 次提交")
        task_id = submit(TEST_IMAGE_URL, TEST_MODEL_IMAGE_URL)
        if task_id:
            ok_count += 1
        time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"提交阶段结果：成功 {ok_count}/{REPEAT}")
    print("=" * 60)

    if ok_count == 0:
        print("\n全部提交失败，跳过轮询/下载。")
        return

    print("\n用最后一次成功的任务做轮询 + 下载验证 ...")
    task_id = submit(TEST_IMAGE_URL, TEST_MODEL_IMAGE_URL)
    if not task_id:
        return
    result_urls = poll_result(task_id, interval=5, max_wait=300)
    if not result_urls:
        return

    if download(result_urls[0], OUTPUT_PATH):
        size_kb = os.path.getsize(OUTPUT_PATH) // 1024
        print(f"[OK] 下载成功，文件大小: {size_kb} KB，保存于 {OUTPUT_PATH}")
    else:
        print("[FAIL] 下载失败")


if __name__ == "__main__":
    main()
