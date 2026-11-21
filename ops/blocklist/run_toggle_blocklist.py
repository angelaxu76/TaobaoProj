"""
发布黑名单总开关：暂停 / 恢复拦截（表里数据保持不变）。
暂停后 generate_publication_excels 不再拦截任何商品；恢复后按原名单继续拦截。
run_cross_store_bad_products 在暂停期间仍会照常往表里写入。
"""
from common.publication.publish_blocklist import is_blocklist_enabled, set_blocklist_enabled, read_blocklist

ENABLED = False   # False = 暂停拦截；True = 恢复拦截

if __name__ == "__main__":
    before = is_blocklist_enabled()
    set_blocklist_enabled(ENABLED)
    n = int(read_blocklist(active_only=True).shape[0])
    state = "✅ 已启用" if ENABLED else "⏸️ 已暂停"
    print(f"{state} 发布黑名单拦截（之前：{'启用' if before else '暂停'}；表内启用中的编码 {n} 个，数据未改动）")
