"""
把 {编码}_{1..9}.jpg 按固定顺序重排编号：原来的 1,6,2,3,5,4,7,8,9 依次改成
1,2,3,4,5,6,7,8,9（即 6->2, 2->3, 3->4, 4->6，1/5/7/8/9 位置不变）。

新旧后缀都是数字（不像 Camper 的字母、ECCO 的视角名那样天然不会撞名，
"改名前"和"改名后"用的是同一套数字），这带来两个坑：

1. 直接顺序改名会互相覆盖——比如"把 2 改成 3"的同时又要"把 3 改成 4"，
   所以这里先把所有需要动的文件改成临时名，等目标位置都空出来了，再统一
   改成最终编号。

2. 因为改完名之后后缀仍然是数字，没法从后缀本身分辨"这批文件是原始下载的
   还是已经改过名的"，如果同一批文件被误跑两次，会把这个置换再套用一次，
   打乱顺序（4 元环 (2 3 4 6) 的平方是两个对换 (2 4)(3 6)，结果是错的）。
   所以每处理完一个编码，会在文件夹里留一个隐藏标记文件
   .clarks_rename_done_{编码}，下次跑到同一个编码时直接跳过。如果确实需要
   重新处理某个编码（比如重新下载过這个编码的图），手动删掉对应的标记文件
   即可。

只用于 CLARKS["IMAGE_DOWNLOAD"]（重命名之后再上传 R2 / 供 AI 视角旋转 /
裁剪合并使用），改名是原地进行的。
"""
import os

SUFFIX_ORDER = [1, 6, 2, 3, 5, 4, 7, 8, 9]
_VALUE_TO_NUMBER = {v: i for i, v in enumerate(SUFFIX_ORDER, start=1)}

_TEMP_SUFFIX = ".__rename_tmp__"
_DONE_MARKER_PREFIX = ".clarks_rename_done_"


def rename_reordered_suffix(folder) -> None:
    folder = str(folder)

    codes_seen = set()
    for filename in os.listdir(folder):
        stem, ext = os.path.splitext(filename)
        if "_" not in stem or not ext:
            continue
        code, suffix = stem.rsplit("_", 1)
        if suffix.isdigit():
            codes_seen.add(code)

    already_done = {
        code for code in codes_seen
        if os.path.exists(os.path.join(folder, f"{_DONE_MARKER_PREFIX}{code}"))
    }
    if already_done:
        print(f"⚠️ 以下编码之前已经改过名，跳过（如需强制重做，删除对应的 "
              f"{_DONE_MARKER_PREFIX}{{编码}} 标记文件）：{sorted(already_done)}")

    pending = []
    for filename in os.listdir(folder):
        stem, ext = os.path.splitext(filename)
        if "_" not in stem:
            continue
        code, suffix = stem.rsplit("_", 1)
        if code in already_done or not suffix.isdigit():
            continue
        number = _VALUE_TO_NUMBER.get(int(suffix))
        if number is None or number == int(suffix):
            continue  # 不在映射表里，或者改名前后编号相同（1/5/7/8/9），不用挪文件
        pending.append((os.path.join(folder, filename), os.path.join(folder, f"{code}_{number}{ext}")))

    if pending:
        # 第一遍：全部挪到临时名，把目标位置腾空
        temp_pairs = []
        for src, dst in pending:
            tmp = src + _TEMP_SUFFIX
            os.rename(src, tmp)
            temp_pairs.append((tmp, dst))

        # 第二遍：临时名 -> 最终编号
        for tmp, dst in temp_pairs:
            if os.path.exists(dst):
                print(f"⚠️ 目标文件已存在，跳过改名: {dst}")
                continue
            os.rename(tmp, dst)
            print(f"✅ 改名: {os.path.basename(tmp)[:-len(_TEMP_SUFFIX)]} -> {os.path.basename(dst)}")
    else:
        print("没有需要改名的文件。")

    for code in codes_seen - already_done:
        open(os.path.join(folder, f"{_DONE_MARKER_PREFIX}{code}"), "w").close()

    print("🚀 编号重排改名完成！")
