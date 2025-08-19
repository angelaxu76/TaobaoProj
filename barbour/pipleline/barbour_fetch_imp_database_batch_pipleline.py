import multiprocessing as mp
import traceback
import sys
from pathlib import Path

# ==== 你现有的导入 ====
from barbour.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from barbour.supplier.barbour_get_links import barbour_get_links
from barbour.supplier.barbour_fetch_info import fetch_and_write_txt
from barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from barbour.supplier.outdoorandcountry_fetch_info import fetch_outdoor_product_offers_concurrent
from barbour.supplier.allweathers_fetch_info import fetch_allweathers_products
from barbour.supplier.allweathers_get_links import allweathers_get_links
from barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
from barbour.supplier.houseoffraser_fetch_info import houseoffraser_fetch_all


# ========= 通用：进程级超时执行器 =========
def _runner(fn, args, kwargs, q):
    """子进程里执行任务，把异常回传给父进程。"""
    try:
        fn(*args, **kwargs)
        q.put(("ok", None))
    except Exception:
        q.put(("error", traceback.format_exc()))

def run_with_timeout(step_name, fn, timeout_sec, *args, **kwargs):
    """
    在独立进程内运行 fn，超时就强制终止。
    返回 True/False 表示是否成功（超时或异常都返回 False，但不会阻塞整个 pipeline）
    """
    q = mp.Queue()
    p = mp.Process(target=_runner, args=(fn, args, kwargs, q), name=f"{step_name}")
    p.start()
    p.join(timeout=timeout_sec)

    if p.is_alive():
        print(f"⏰ 超时，正在终止步骤：{step_name}（>{timeout_sec}s）")
        p.terminate()
        p.join(5)
        print(f"🛑 已杀死超时进程：{step_name}")
        return False

    try:
        status, payload = q.get_nowait()
    except Exception:
        # 没有返回，也当失败处理
        print(f"⚠️ 步骤无返回：{step_name}")
        return False

    if status == "ok":
        print(f"✅ 完成：{step_name}")
        return True
    else:
        print(f"❌ 出错：{step_name}\n{payload}")
        return False


# ========= 安全版 Pipeline（不改你的函数签名/内部逻辑）=========
def barbour_database_import_pipleline_safe():
    print("\n🌐 步骤 1：抓取商品链接（每站点单独超时）")
    run_with_timeout("barbour_get_links", barbour_get_links, 180)
    run_with_timeout("outdoorandcountry_get_links", outdoorandcountry_fetch_and_save_links, 300)
    run_with_timeout("allweathers_get_links", allweathers_get_links, 300)
    run_with_timeout("houseoffraser_get_links", houseoffraser_get_links, 300)

    print("\n🧰 步骤 2：抓取商品详情并写 TXT（每站点设总时长上限）")
    # Barbour 官网
    run_with_timeout("barbour_fetch_and_write_txt", fetch_and_write_txt, 3600)
    # Outdoor & Country（内部自己多线程），给一个总超时
    run_with_timeout("outdoorandcountry_fetch_info", fetch_outdoor_product_offers_concurrent, 3600, max_workers=15)
    # Allweathers
    run_with_timeout("allweathers_fetch_info", fetch_allweathers_products, 3000, 7)  # 7 = max_workers
    # House of Fraser
    run_with_timeout("houseoffraser_fetch_all", houseoffraser_fetch_all, 3000)

    print("\n📥 步骤 3：导入 barbour_products（按供应商分开导，避免一个出问题影响其它）")
    # 你也可以先来一次全量（如果目录很大，这步可能更慢）
    # run_with_timeout("import_products_all", batch_import_txt_to_barbour_product, 600, "all")
    run_with_timeout("import_products_barbour", batch_import_txt_to_barbour_product, 600, "barbour")
    run_with_timeout("import_products_oac", batch_import_txt_to_barbour_product, 900, "outdoorandcountry")
    run_with_timeout("import_products_allweathers", batch_import_txt_to_barbour_product, 900, "allweathers")
    run_with_timeout("import_products_hof", batch_import_txt_to_barbour_product, 900, "houseoffraser")

    print("\n💾 步骤 4：导入 offers（库存/价格）")
    run_with_timeout("import_offers_barbour", import_txt_for_supplier, 600, "barbour")
    run_with_timeout("import_offers_oac", import_txt_for_supplier, 900, "outdoorandcountry")
    run_with_timeout("import_offers_allweathers", import_txt_for_supplier, 900, "allweathers")
    run_with_timeout("import_offers_hof", import_txt_for_supplier, 900, "houseoffraser")

    print("\n🎉 全流程完成（超时的步骤已被自动跳过/终止，不会卡住主进程）")


if __name__ == "__main__":
    # Windows 上用多进程需放在 main 保护下
    mp.set_start_method("spawn", force=True)
    barbour_database_import_pipleline_safe()
