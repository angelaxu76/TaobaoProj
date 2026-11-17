# -*- coding: utf-8 -*-
"""
Barbour 多机运行 —— 副机：只抓自己那部分供货商

可以和主机同时启动（或先于主机启动）：开抓前会自动等待主机备份清空完成
（轮询 _ROUND_STARTED.json），参数见 session_config.py 的 WORKER_WAIT_ROUND_*。

节点档案见 brands/barbour/pipeline/session_config.py 的 NODE_PROFILES["worker"]。
超时/重试等参数沿用 ops/run_barbour_jingya_listing.py 的 CONFIG。
"""

import sys

from ops.run_barbour_jingya_listing import main

NODE = "worker"

if __name__ == "__main__":
    sys.exit(main(NODE))
