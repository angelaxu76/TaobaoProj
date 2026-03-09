"""
LinkFox (Ziniao) AI换模特-2.0 API 客户端。

接口：/linkfox-ai/image/v2/make/changeModelFixed
功能：以原始模特拍摄图为底，替换目标模特的头部/面部，服装结构不变。

主要参数：
  imageUrl       — 原始模特图（源图，含服装）
  modelImageUrl  — 目标模特头部参考图
  imageSegUrl    — 原图保留区抠图（可选，提升精度）
  sceneImgUrl    — 场景/背景参考图（可选）
  sceneStrength  — 场景相似度 [0.0, 1.0]，默认 0.7
  genOriRes      — 是否输出原始分辨率（默认 False）
  realModel      — 是否为真人模特（默认 True）
  outputNum      — 输出张数 [1, 4]，默认 1

典型用法：
    client = LinkFoxClient(api_key="你的Key")
    task_id = client.submit(
        image_url="https://...",
        model_image_url="https://...",
    )
    result_urls = client.poll_result(task_id)
"""
import time
import requests

LINKFOX_HOST         = "https://sbappstoreapi.ziniao.com/openapi-router"
LINKFOX_SUBMIT_PATH  = "/linkfox-ai/image/v2/make/changeModelFixed"
# 结果查询路径（POST，body: {"id": task_id}）
# 已知 /get/makeResult 返回 40002，请根据官方文档确认正确路径后更新
LINKFOX_RESULT_PATH  = "/linkfox-ai/image/v2/make/info"
# 刷新图片地址接口（图片 URL 8小时后过期，用此接口换新 URL）
LINKFOX_REFRESH_PATH = "/linkfox-ai/image/v2/info"


class LinkFoxClient:
    """LinkFox (Ziniao) AI换模特-2.0 API 客户端。"""

    def __init__(self, api_key: str, host: str = LINKFOX_HOST):
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
        gen_ori_res: bool = False,
        real_model: bool = True,
        output_num: int = 1,
    ) -> str | None:
        """提交换模特任务，返回任务 ID（成功）或 None（失败）。

        Args:
            image_url:        原始模特图 URL（含服装，AI 保留服装结构）
            model_image_url:  目标模特头部/面部参考图 URL
            image_seg_url:    原图保留区抠图结果 URL（可选，提升换脸精度）
            scene_img_url:    场景/背景参考图 URL（可选）
            scene_strength:   场景相似度 [0.0, 1.0]，默认 0.7（为 None 时不传）
            gen_ori_res:      是否生成原分辨率图，默认 False
            real_model:       是否为真人模特，默认 True
            output_num:       输出张数 [1, 4]，默认 1

        Returns:
            任务 ID 字符串（成功），或 None（提交失败）
        """
        payload: dict = {
            "imageUrl":       image_url,
            "modelImageUrl":  model_image_url,
            "genOriRes":      gen_ori_res,
            "realModel":      real_model,
            "outputNum":      output_num,
        }
        if image_seg_url:
            payload["imageSegUrl"] = image_seg_url
        if scene_img_url:
            payload["sceneImgUrl"] = scene_img_url
        if scene_strength is not None:
            payload["sceneStrength"] = str(scene_strength)

        try:
            resp = requests.post(
                f"{self.host}{LINKFOX_SUBMIT_PATH}",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
            if not resp.ok:
                print(f"[LinkFox] 提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
                return None
            body = resp.json()
        except Exception as e:
            print(f"[LinkFox] 提交请求异常: {e}")
            return None

        code = str(body.get("code", ""))
        if code != "0":
            sub_msg = body.get("sub_msg") or body.get("msg") or "未知错误"
            print(f"[LinkFox] 提交失败 (code={code}): {sub_msg}")
            return None

        outer_data = body.get("data") or {}
        task_id = (outer_data.get("data") or outer_data).get("id")
        if not task_id:
            print(f"[LinkFox] 提交成功但未返回 task_id，完整响应: {body}")
            return None

        print(f"[LinkFox] 任务已提交，ID: {task_id}")
        return str(task_id)

    # ------------------------------------------------------------------
    # 轮询结果
    # ------------------------------------------------------------------
    def poll_result(
        self,
        task_id: str,
        interval: int = 5,
        max_wait: int = 300,
    ) -> list[str]:
        """轮询任务直到完成，返回结果图片 URL 列表。

        状态码（官方文档）：
          1 = 排队中
          2 = 生成中
          3 = 成功
          4 = 失败

        Args:
            task_id:  submit() 返回的任务 ID
            interval: 轮询间隔（秒），默认 5
            max_wait: 最长等待时间（秒），默认 300

        Returns:
            成功时返回图片 URL 列表，失败或超时时返回空列表。
            注意：URL 有效期 8 小时，过期后用 refresh_image_url() 刷新。
        """
        endpoint = f"{self.host}{LINKFOX_RESULT_PATH}"
        elapsed  = 0
        print(f"[LinkFox] 轮询任务结果，ID: {task_id} ...")

        while elapsed < max_wait:
            try:
                resp = requests.post(
                    endpoint,
                    headers=self._headers,
                    json={"id": task_id},
                    timeout=15,
                )
                resp.raise_for_status()
                body = resp.json()
            except Exception as e:
                print(f"[LinkFox] 轮询异常（已等待 {elapsed}s）: {e}")
                body = {}

            # 响应外层：{"code": "0", "data": {...}}
            # 响应内层 data：{"code": 200, "data": {"id":..., "status":..., "resultList":[...]}}
            outer_code = str(body.get("code", ""))
            outer_data = body.get("data") or {}
            inner_data = (outer_data.get("data") or outer_data)

            if outer_code == "0":
                status = inner_data.get("status")

                if status == 3:  # 成功
                    result_list = inner_data.get("resultList") or []
                    urls = [
                        item["url"] for item in result_list
                        if item.get("status") == 1 and item.get("url")
                    ]
                    if urls:
                        print(f"[LinkFox] 生成成功，共 {len(urls)} 张: {urls}")
                        return urls
                    print(f"[LinkFox] status=3 但结果 URL 为空，原始 data: {inner_data}")
                    return []

                elif status == 4:  # 失败
                    reason = inner_data.get("errorMsg") or "未知原因"
                    print(f"[LinkFox] 任务失败 (id={task_id}): {reason}")
                    return []

                else:  # 1=排队中, 2=生成中
                    label = {1: "排队中", 2: "生成中"}.get(status, f"status={status}")
                    print(f"[LinkFox] {label}，已等待 {elapsed}s ...")

            elif body:
                msg = (outer_data.get("msg")
                       or body.get("sub_msg")
                       or body.get("msg") or "")
                print(f"[LinkFox] 查询返回异常 (code={outer_code}): {msg} | 完整响应: {body}")

            time.sleep(interval)
            elapsed += interval

        print(f"[LinkFox] 超时（{max_wait}s），任务 {task_id} 未完成")
        return []

    def refresh_image_url(self, image_id: str | int, download_format: str = "jpg") -> str | None:
        """刷新过期图片地址（图片 URL 有效期 8 小时）。

        Args:
            image_id:        resultList 中每张图片的 id（非任务 ID）
            download_format: 下载格式，默认 "jpg"

        Returns:
            新的图片 URL（成功），或 None（失败）
        """
        try:
            resp = requests.post(
                f"{self.host}{LINKFOX_REFRESH_PATH}",
                headers=self._headers,
                json={"id": int(image_id), "downloadFormat": download_format},
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            print(f"[LinkFox] 刷新图片地址异常: {e}")
            return None

        outer_data = body.get("data") or {}
        inner_data = outer_data.get("data") or outer_data
        url = inner_data.get("url")
        if url:
            return url
        print(f"[LinkFox] 刷新图片地址失败，响应: {body}")
        return None

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
        gen_ori_res: bool = False,
        real_model: bool = True,
        output_num: int = 1,
        poll_interval: int = 5,
        max_wait: int = 300,
    ) -> list[str]:
        """提交换模特任务并等待完成，返回结果图片 URL 列表。

        参数同 submit()，额外：
            poll_interval: 轮询间隔（秒）
            max_wait:      最长等待时间（秒）

        Returns:
            结果图片 URL 列表，失败时返回空列表。
        """
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
