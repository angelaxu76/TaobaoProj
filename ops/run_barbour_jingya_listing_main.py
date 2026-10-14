# -*- coding: utf-8 -*-
"""
Barbour 多机运行 —— 主机：先启动，清空 publication，抓自己那部分供货商，等全部 TXT 就绪后跑 B/C/D

节点档案见 brands/barbour/pipeline/session_config.py 的 NODE_PROFILES["main"]。
超时/重试等参数沿用 ops/run_barbour_jingya_listing.py 的 CONFIG。
"""

import sys

from ops.run_barbour_jingya_listing import main

NODE = "main"

if __name__ == "__main__":
    sys.exit(main(NODE))
