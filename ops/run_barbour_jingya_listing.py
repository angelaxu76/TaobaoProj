# -*- coding: utf-8 -*-
"""
Barbour prepare_jingya_listing 独立执行入口

用法：
  python ops/run_barbour_jingya_listing.py

Barbour 供应商多、抓取耗时远超鞋类品牌（clarks/camper/ecco/geox），
单独拆出来跑在自己的虚拟机上，与鞋类品牌互不阻塞。鞋类品牌见
ops/run_all_jingya_listing.py。

配置：
  修改下方 CONFIG 区域来调整超时时间、循环间隔、重试次数。
  执行引擎（子进程管理 + 看门狗 + 日志）见 ops/_jingya_runner.py。
"""

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
LOOP_ENABLED = True

# 每轮结束后等待多少秒再开始下一轮（默认 2 小时）
LOOP_INTERVAL_SEC = 7200


if __name__ == "__main__":
    sys.exit(run_pipeline(
        title="Barbour Jingya Listing 流水线",
        brands_to_run=BRANDS_TO_RUN,
        log_name_prefix="run_barbour_jingya",
        continue_on_failure=CONTINUE_ON_FAILURE,
        silence_timeout_sec=SILENCE_TIMEOUT_SEC,
        max_retries=MAX_RETRIES,
        loop_enabled=LOOP_ENABLED,
        loop_interval_sec=LOOP_INTERVAL_SEC,
    ))
