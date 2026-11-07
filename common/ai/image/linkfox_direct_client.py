"""
LinkFox 官方 API 直连客户端（AI换模特-2.0，不经过紫鸟开放平台）。

文档：
  https://wiki.linkfox.com/docs/linkfox-ai/model-swap-v2
  https://wiki.linkfox.com/docs/linkfox-ai/task-result
  https://wiki.linkfox.com/docs/linkfox-ai/refresh-image-url

与紫鸟版 linkfox_client.py 的区别：
  - Base URL：https://ai-api.linkfox.com
  - 路径：去掉 /linkfox-ai 前缀
  - 响应：少包一层，{"code": 200, "msg": ..., "traceId": ..., "data": {...}}
  - 成功码：code=200（紫鸟网关是 "0"）；鉴权失败等错误也是 HTTP 200，必须看 body 的 code
  - 查询间隔：官方要求每次至少 10 秒

方法签名与 LinkFoxClient 一致，可直接传给 process_one_linkfox()。

典型用法：
    client = LinkFoxDirectClient(api_key="你的Key")
    urls = client.change_model_and_wait(
        image_url="https://...",
        model_image_url="https://...",
    )
"""
import time
import requests

LINKFOX_DIRECT_HOST = "https://ai-api.linkfox.com"
SUBMIT_PATH  = "/image/v2/make/changeModelFixed"
RESULT_PATH  = "/image/v2/make/info"
REFRESH_PATH = "/image/v2/info"

MIN_POLL_INTERVAL = 10  # 官方要求：查询任务结果至少间隔 10 秒

# 重试也不会成功的错误：立即停止，不再重试/轮询
FATAL_MSG_KEYS = {
    "ERR_AUTHENTICATION_FAIL",      # Key 无效
    "ERR_FILED_VALIDATE",           # 参数不符合要求（官方拼写即 FILED）
    "ERR_VALIDATE_FAIL",            # 参数校验未通过
    "ERR_IMAGE_MAKE_AUDIT",         # 图片/内容未通过审核
    "ERR_IMAGE_MAKE_WILL_OUT",      # 点数不足
    "ERR_FORBIDDEN",                # 当前团队无权访问该任务
    "ERR_NOT_HAVE_TEAM_PRIVILEGE",  # 账号未绑定团队
    "TEAM_PERMISSION_DISABLE_USER", # 账号已禁用
    "TEAM_PERMISSION_EXPIRE",       # 套餐过期或未购买
}


def _is_ok(body: dict) -> bool:
    # 官方示例中 code 既有数字 200 也有字符串 "200"
    return str(body.get("code", "")) == "200"


def _describe_error(body: dict) -> str:
    return (f"code={body.get('code')} msgKey={body.get('msgKey')} "
            f"msg={body.get('msg')} traceId={body.get('traceId')}")


class LinkFoxDirectClient:
    """LinkFox 官方 API 直连客户端。"""

    def __init__(self, api_key: str, host: str = LINKFOX_DIRECT_HOST):
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
        image_url: str,
        model_image_url: str,
        *,
        image_seg_url: str | None = None,
        scene_img_url: str | None = None,
        scene_strength: float | None = None,
        gen_ori_res: bool | None = None,
        real_model: bool | None = None,
        output_num: int | None = None,
    ) -> str | None:
        """提交换模特任务，返回任务 ID（成功）或 None（失败）。

        Args:
            image_url:        模特原图 URL（jpg/jpeg/png/webp，20M 内，385~8192 像素）
            model_image_url:  模特头部图 URL
            image_seg_url:    原图保留区抠图结果 URL（可选）
            scene_img_url:    场景图 URL（可选）
            scene_strength:   场景相似度 [0, 1]（None 时不传，接口默认 0.7）
            gen_ori_res:      是否生成原分辨率图（None 时不传，接口默认 False；每张 25 点）
            real_model:       原图是否真人模特，False 为人台（None 时不传，接口默认 True）
            output_num:       输出张数 [1, 4]（None 时不传，接口默认 1）
        """
        payload: dict = {
            "imageUrl":      image_url,
            "modelImageUrl": model_image_url,
        }
        if image_seg_url:
            payload["imageSegUrl"] = image_seg_url
        if scene_img_url:
            payload["sceneImgUrl"] = scene_img_url
        if scene_strength is not None:
            payload["sceneStrength"] = str(scene_strength)  # 文档类型为 string
        if gen_ori_res is not None:
            payload["genOriRes"] = gen_ori_res
        if real_model is not None:
            payload["realModel"] = real_model
        if output_num is not None:
            payload["outputNum"] = output_num

        max_attempts = 5
        retry_delay  = 5

        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    f"{self.host}{SUBMIT_PATH}",
                    headers=self._headers,
                    json=payload,
                    timeout=30,
                )
                body = resp.json()
            except requests.exceptions.ReadTimeout as e:
                # 服务端可能已建任务，重发有重复扣点风险，不重试
                print(f"[LinkFox] 提交超时，不重试以免重复扣点: {e}")
                return None
            except Exception as e:
                print(f"[LinkFox] 提交请求异常 ({attempt}/{max_attempts}): {e}")
                if attempt < max_attempts:
                    time.sleep(retry_delay)
                    continue
                return None

            task_id = (body.get("data") or {}).get("id") if _is_ok(body) else None
            if task_id:
                print(f"[LinkFox] 任务已提交，ID: {task_id}")
                return str(task_id)

            print(f"[LinkFox] 提交失败 ({attempt}/{max_attempts}): {_describe_error(body)}")
            if body.get("msgKey") in FATAL_MSG_KEYS:
                return None
            if attempt < max_attempts:
                time.sleep(retry_delay)

        return None

    # ------------------------------------------------------------------
    # 轮询结果
    # ------------------------------------------------------------------
    def poll_result(
        self,
        task_id: str,
        interval: int = MIN_POLL_INTERVAL,
        max_wait: int = 300,
    ) -> list[str]:
        """轮询任务直到完成，返回结果图片 URL 列表。

        任务状态 data.status：1=排队中 2=生成中 3=成功 4=失败
        图片状态 resultList[].status：0=生成中 1=成功 2=失败

        Args:
            task_id:  submit() 返回的任务 ID
            interval: 轮询间隔（秒），低于 10 时按 10 处理
            max_wait: 最长等待时间（秒）

        Returns:
            成功时返回图片 URL 列表，失败或超时时返回空列表。
        """
        interval = max(interval, MIN_POLL_INTERVAL)
        elapsed  = 0
        print(f"[LinkFox] 轮询任务结果，ID: {task_id} ...")

        while elapsed < max_wait:
            body: dict = {}
            try:
                resp = requests.post(
                    f"{self.host}{RESULT_PATH}",
                    headers=self._headers,
                    json={"id": str(task_id)},  # int64，按字符串传避免精度问题
                    timeout=15,
                )
                body = resp.json()
            except Exception as e:
                print(f"[LinkFox] 轮询异常（已等待 {elapsed}s）: {e}")

            if body and not _is_ok(body):
                print(f"[LinkFox] 查询返回异常: {_describe_error(body)}")
                if body.get("msgKey") in FATAL_MSG_KEYS:
                    return []
            elif body:
                data   = body.get("data") or {}
                status = data.get("status")

                if status == 3:
                    results = data.get("resultList") or []
                    urls = [r["url"] for r in results if r.get("status") == 1 and r.get("url")]
                    for r in results:
                        if r.get("status") == 2:
                            print(f"[LinkFox] 单张失败 (id={r.get('id')}): "
                                  f"{r.get('errorCode')} {r.get('errorMsg')}")
                    if urls:
                        print(f"[LinkFox] 生成成功，共 {len(urls)} 张，消耗 {data.get('count')} 点")
                    else:
                        print(f"[LinkFox] status=3 但结果 URL 为空，原始 data: {data}")
                    return urls

                if status == 4:
                    print(f"[LinkFox] 任务失败 (id={task_id}): "
                          f"{data.get('errorCode')} {data.get('errorMsg') or '未知原因'}")
                    return []

                label = {1: "排队中", 2: "生成中"}.get(status, f"status={status}")
                print(f"[LinkFox] {label}，已等待 {elapsed}s ...")

            time.sleep(interval)
            elapsed += interval

        print(f"[LinkFox] 超时（{max_wait}s），任务 {task_id} 未完成")
        return []

    # ------------------------------------------------------------------
    # 刷新图片地址
    # ------------------------------------------------------------------
    def refresh_image_url(self, image_id: str | int, download_format: str = "jpg") -> str | None:
        """用图片 ID（resultList[].id，不是任务 ID）换取新的图片地址。"""
        try:
            resp = requests.post(
                f"{self.host}{REFRESH_PATH}",
                headers=self._headers,
                json={"id": int(image_id), "downloadFormat": download_format},
                timeout=15,
            )
            body = resp.json()
        except Exception as e:
            print(f"[LinkFox] 刷新图片地址异常: {e}")
            return None

        url = (body.get("data") or {}).get("url") if _is_ok(body) else None
        if not url:
            print(f"[LinkFox] 刷新图片地址失败: {_describe_error(body)}")
        return url

    # ------------------------------------------------------------------
    # 一步到位：提交 + 轮询
    # ------------------------------------------------------------------
    def change_model_and_wait(
        self,
        image_url: str,
        model_image_url: str,
        *,
        image_seg_url: str | None = None,
        scene_img_url: str | None = None,
        scene_strength: float | None = None,
        gen_ori_res: bool | None = None,
        real_model: bool | None = None,
        output_num: int | None = None,
        poll_interval: int = MIN_POLL_INTERVAL,
        max_wait: int = 300,
    ) -> list[str]:
        """提交换模特任务并等待完成，返回结果图片 URL 列表（失败时为空列表）。"""
        task_id = self.submit(
            image_url=image_url,
            model_image_url=model_image_url,
            image_seg_url=image_seg_url,
            scene_img_url=scene_img_url,
            scene_strength=scene_strength,
            gen_ori_res=gen_ori_res,
            real_model=real_model,
            output_num=output_num,
        )
        if not task_id:
            return []
        return self.poll_result(task_id, interval=poll_interval, max_wait=max_wait)
