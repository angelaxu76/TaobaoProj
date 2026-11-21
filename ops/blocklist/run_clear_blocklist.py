"""
清空发布黑名单表（删除全部记录）。
⚠️ 只是想临时不拦截，请用 run_toggle_blocklist.py 暂停，数据不会丢。

清空前自动导出一份 Excel 备份（含 ID、原因、开关等），需要时可用 run_import_blocklist_excel.py 导回
（导回能恢复：商品编码 / 品牌 / 启用 / 打折后可发布 / 原因 / 备注；加入时价格、加入次数、时间等不能恢复）。
"""
from datetime import datetime

from common.publication.publish_blocklist import clear_blocklist, read_blocklist
from ops.blocklist.blocklist_excel import export_to_excel
from ops.blocklist.run_export_blocklist_excel import _default_dir

CONFIRM = False   # 改成 True 才会真正执行清空

if __name__ == "__main__":
    n = len(read_blocklist())
    if not CONFIRM:
        print(f"⚠️ 表内共 {n} 个编码。确认要清空请把 CONFIRM 改为 True 再运行；"
              f"只想临时停用请用 run_toggle_blocklist.py")
    elif n == 0:
        print("ℹ️ 黑名单表已经是空的")
    else:
        backup = export_to_excel(_default_dir() / f"publish_blocklist_backup_before_clear_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
        print(f"💾 已备份：{backup}")
        print(f"🗑️ 已清空发布黑名单：删除 {clear_blocklist()} 个编码")
