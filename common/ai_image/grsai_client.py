"""
GrsAI nano-banana 图片生成客户端。

支持模型（model 参数）：
  nano-banana-pro-vt   虚拟试穿（Virtual Try-on）
  nano-banana-pro-cl   服装生成（Clothing）

典型用法：
    from common.ai_image.grsai_client import GrsAIClient

    client = GrsAIClient(api_key="你的Key")
    image_url = client.generate_and_wait(
        urls=[flat_url, detail_url, model_url],
        prompt="...",
        model="nano-banana-pro-vt",
    )
"""
import time
import requests

GRSAI_HOST = "https://grsaiapi.com"


class GrsAIClient:
    """GrsAI nano-banana API 客户端。"""

    def __init__(self, api_key: str, host: str = GRSAI_HOST):
        self.host = host.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    # ------------------------------------------------------------------
    # 提交任务
    # ------------------------------------------------------------------
    def submit(
        self,
        urls: list[str],
        prompt: str,
        model: str = "nano-banana-pro-vt",
        aspect_ratio: str = "3:4",
        image_size: str = "1K",
        negative_prompt: str | None = None,
    ) -> dict:
        """提交生图任务，立即返回 API 原始响应（含 data.id）。

        Args:
            urls:             图片 URL 列表，2-5 张，顺序即 img_1…img_n
            prompt:           英文提示词，用 img_n 指代各图角色
            model:            模型名称
            aspect_ratio:     图片比例，如 "3:4"
            image_size:       图片分辨率，如 "1K" / "2K"
            negative_prompt:  负向提示词（可选），API 支持时生效

        Returns:
            API 原始响应 dict
        """
        if not isinstance(urls, list) or len(urls) < 2:
            raise ValueError("urls 必须是至少 2 张图片的列表")

        payload = {
            "model": model,
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "imageSize": image_size,
            "urls": urls,
            "webHook": "-1",      # 不用 webhook，改用轮询
            "shutProgress": True,
        }
        if negative_prompt:
            payload["negativePrompt"] = negative_prompt
        resp = requests.post(
            f"{self.host}/v1/draw/nano-banana",
            headers=self._headers,
            json=payload,          # 比 data=json.dumps() 更标准
            timeout=30,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            print(f"[GrsAI] submit 非JSON响应: {resp.text[:300]}")
            raise

    # ------------------------------------------------------------------
    # 轮询结果
    # ------------------------------------------------------------------
    def poll_result(self, task_id: str, interval: int = 3, max_wait: int = 600) -> str | None:
        """轮询任务直到完成，返回结果图片 URL。

        前 60s 每 `interval` 秒轮询一次；之后每 `interval * 3` 秒一次（减少请求压力）。

        Args:
            task_id:   submit() 返回的任务 ID
            interval:  快轮阶段间隔（秒），默认 3
            max_wait:  最长等待时间（秒），默认 600

        Returns:
            成功时返回图片 URL 字符串，失败或超时返回 None
        """
        endpoint = f"{self.host}/v1/draw/result"
        elapsed = 0
        print(f"[GrsAI] 任务已提交，ID: {task_id}，轮询中...")

        while elapsed < max_wait:
            try:
                resp = requests.post(
                    endpoint,
                    headers=self._headers,   # fix: 带上 Authorization
                    json={"id": task_id},
                    timeout=15,
                )
                resp.raise_for_status()
                body = resp.json()
            except Exception as e:
                # 网络抖动 / 网关返回 HTML 时不崩，打印原始文本后继续等
                raw = getattr(e, "response", None)
                raw_text = raw.text[:300] if raw is not None else str(e)
                print(f"[GrsAI] 轮询异常（已等待 {elapsed}s）: {raw_text}")
                body = {}

            if body.get("code") == 0:
                data = body["data"]
                status = data.get("status")

                if status == "succeeded":
                    results = data.get("results") or []
                    url = results[0].get("url") if results else None
                    if url:
                        print(f"[GrsAI] 生成成功: {url}")
                        return url
                    print(f"[GrsAI] succeeded 但 results 为空: {data}")
                    return None

                elif status == "failed":
                    reason = data.get("failure_reason", "未知原因")
                    print(f"[GrsAI] 生成失败（任务 {task_id}）: {reason}")
                    return None

                else:
                    print(f"[GrsAI] 状态: {status}，已等待 {elapsed}s...")

            elif body:
                print(f"[GrsAI] 查询异常: {body.get('msg')}")

            # 自适应间隔：前 60s 快轮，之后放慢
            sleep_sec = interval if elapsed < 60 else interval * 3
            time.sleep(sleep_sec)
            elapsed += sleep_sec

        print(f"[GrsAI] 超时（{max_wait}s），任务 {task_id} 未完成")
        return None

    # ------------------------------------------------------------------
    # 一步到位：提交 + 轮询
    # ------------------------------------------------------------------
    def generate_and_wait(
        self,
        urls: list[str],
        prompt: str = (
            "High-fidelity virtual try-on. img_1 is the target model (identity and pose). "
            "img_2 is the flat garment. img_3 is the fabric texture detail. "
            "Dress the model with the garment, strictly preserving all structural details."
        ),
        model: str = "nano-banana-pro-vt",
        aspect_ratio: str = "3:4",
        image_size: str = "1K",
        negative_prompt: str | None = None,
        poll_interval: int = 3,
        max_wait: int = 600,
    ) -> str | None:
        """提交任务并等待完成，返回结果图片 URL。

        Args:
            urls:             图片 URL 列表，顺序即 img_1…img_n
            prompt:           英文提示词（有默认值）
            model:            模型名称
            aspect_ratio:     图片比例
            image_size:       图片分辨率，如 "1K" / "2K"
            negative_prompt:  负向提示词（可选）
            poll_interval:    快轮阶段间隔（秒）
            max_wait:         最长等待时间（秒）

        Returns:
            结果图片 URL，或 None
        """
        task_res = self.submit(urls, prompt, model, aspect_ratio, image_size, negative_prompt)

        if task_res.get("code") != 0:
            print(f"[GrsAI] 提交任务失败: {task_res.get('msg')}")
            return None

        task_id = task_res["data"]["id"]
        return self.poll_result(task_id, interval=poll_interval, max_wait=max_wait)
