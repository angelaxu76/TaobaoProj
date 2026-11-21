"""
发布黑名单运营脚本（数据在 PostgreSQL 表 publish_blocklist，核心逻辑在 common/publication/publish_blocklist.py）

| 脚本                              | 用途                                                            |
|-----------------------------------|-----------------------------------------------------------------|
| run_init_blocklist.py             | 建表 + 从旧 Excel（publish_blocklist.xlsx）迁移，可重复执行       |
| run_refresh_discount.py           | 刷新黑名单商品当前是否打折（发布时也会自动刷新）                   |
| run_export_blocklist_excel.py     | 导出整张表到 Excel，便于查看/批量修改                             |
| run_import_blocklist_excel.py     | 把改过的 Excel 导回数据库（启用 / 打折后可发布 / 品牌 / 备注）     |
| run_add_codes.py                  | 手动把商品编码加入黑名单                                         |
| run_remove_codes.py               | 手动解除拦截（记录保留，is_active = FALSE）                        |
| run_toggle_blocklist.py           | 总开关：暂停 / 恢复整个黑名单拦截（数据不变，临时屏蔽用这个）       |
| run_clear_blocklist.py            | 清空整张表（先自动备份 Excel，需 CONFIRM = True）                  |

自动写入：analytics/pipeline/run_cross_store_bad_products.py（价格高+无访问+无折扣 → 加入，打折后可发布=是）
读取过滤：channels/jingya/export/generate_publication_excel_*.py 调用 load_publish_blocklist()

拦截规则：总开关启用 且 is_active 且（release_on_discount = FALSE 或 当前未打折）
总开关存在表 publish_blocklist_settings（key = 'enabled'），没有记录时视为启用。
"""
