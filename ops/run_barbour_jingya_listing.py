# -*- coding: utf-8 -*-
"""
Barbour prepare_jingya_listing 独立执行入口

用法：
  python ops/run_barbour_jingya_listing.py                 # 单机全跑（按 session_config 原值）
  python ops/run_barbour_jingya_listing.py --node main     # 多机：主机
  python ops/run_barbour_jingya_listing.py --node worker   # 多机：副机
  也可直接运行 run_barbour_jingya_listing_main.py / _worker.py（已预设节点）。

  节点档案（各节点抓哪些供货商、跑哪些阶段）在
  brands/barbour/pipeline/session_config.py 的 NODE_PROFILES 里配置，
  通过环境变量 BARBOUR_NODE 传给子进程，不需要再手改 session_config。

Barbour 供应商多、抓取耗时远超鞋类品牌（clarks/camper/ecco/geox），
单独拆出来跑在自己的虚拟机上，与鞋类品牌互不阻塞。鞋类品牌见
ops/run_all_jingya_listing.py。

配置：
  修改下方 CONFIG 区域来调整超时时间、循环间隔、重试次数。
  执行引擎（子进程管理 + 看门狗 + 日志）见 ops/_jingya_runner.py。
"""

import argparse
import os
import sys

from ops._jingya_runner import run_pipeline

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════

BRANDS_TO_RUN = ["barbour"]

# 某个品牌失败后是否继续跑后续品牌（True=继续，False=中止）
CONTINUE_ON_FAILURE = True

# 输出静默超过此秒数视为卡死，自动 kill（Barbour 供应商多、单个耗时更长，放宽到 20 分钟）
SILENCE_TIMEOUT_SEC = 1200

# 卡死后自动重试次数（0 = 不重试，直接标记失败）
MAX_RETRIES = 1

# 是否循环执行（True=跑完一轮后等待 LOOP_INTERVAL_SEC 再重新开始，False=只跑一次）
LOOP_ENABLED = False

# 每轮结束后等待多少秒再开始下一轮（默认 2 小时）
LOOP_INTERVAL_SEC = 7200


def main(node: str | None = None) -> int:
    title = "Barbour Jingya Listing 流水线"
    log_name_prefix = "run_barbour_jingya"
    if node:
        # 子进程继承环境变量，session_config 据此套用 NODE_PROFILES[node]
        os.environ["BARBOUR_NODE"] = node
        title += f"（节点：{node}）"
        log_name_prefix += f"_{node}"
    else:
        os.environ.pop("BARBOUR_NODE", None)

    return run_pipeline(
        title=title,
        brands_to_run=BRANDS_TO_RUN,
        log_name_prefix=log_name_prefix,
        continue_on_failure=CONTINUE_ON_FAILURE,
        silence_timeout_sec=SILENCE_TIMEOUT_SEC,
        max_retries=MAX_RETRIES,
        loop_enabled=LOOP_ENABLED,
        loop_interval_sec=LOOP_INTERVAL_SEC,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Barbour Jingya Listing 流水线")
    parser.add_argument("--node", help="多机节点名（见 session_config.NODE_PROFILES），不填 = 单机全跑")
    sys.exit(main(parser.parse_args().node))
