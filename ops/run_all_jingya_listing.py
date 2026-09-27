# -*- coding: utf-8 -*-
"""
鞋类品牌 prepare_jingya_listing 顺序执行总入口

用法：
  python ops/run_all_jingya_listing.py

Barbour 耗时远超鞋类品牌，已分离到独立虚拟机运行，见
ops/run_barbour_jingya_listing.py。

配置：
  修改下方 CONFIG 区域来启用/禁用品牌、调整超时时间、设置重试次数。
  执行引擎（子进程管理 + 看门狗 + 日志）见 ops/_jingya_runner.py。
"""

import sys

from ops._jingya_runner import run_pipeline

# ══════════════════════════════════════════════════════════════════
#  CONFIG — 修改这里来启用/禁用品牌，或调整执行顺序
# ══════════════════════════════════════════════════════════════════

BRANDS_TO_RUN = [
    "clarks",
    "camper",
    "ecco",
    "geox",
    # "marksandspencer",
]

# 某个品牌失败后是否继续跑后续品牌（True=继续，False=中止）
CONTINUE_ON_FAILURE = True

# 输出静默超过此秒数视为卡死，自动 kill（10 分钟）
SILENCE_TIMEOUT_SEC = 600

# 卡死后自动重试次数（0 = 不重试，直接标记失败）
MAX_RETRIES = 1

# 是否循环执行（True=跑完一轮后等待 LOOP_INTERVAL_SEC 再重新开始，False=只跑一次）
LOOP_ENABLED = False

# 每轮结束后等待多少秒再开始下一轮（默认 2 小时）
LOOP_INTERVAL_SEC = 7200


if __name__ == "__main__":
    sys.exit(run_pipeline(
        title="鞋类品牌 Jingya Listing 流水线",
        brands_to_run=BRANDS_TO_RUN,
        log_name_prefix="run_all_jingya",
        continue_on_failure=CONTINUE_ON_FAILURE,
        silence_timeout_sec=SILENCE_TIMEOUT_SEC,
        max_retries=MAX_RETRIES,
        loop_enabled=LOOP_ENABLED,
        loop_interval_sec=LOOP_INTERVAL_SEC,
    ))
