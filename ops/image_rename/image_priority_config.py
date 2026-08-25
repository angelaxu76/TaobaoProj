"""
各品牌"选图 / 改名"优先级集中配置，避免每次调整要打开一大堆 cfg/brands/*.py。

这个文件和 ops/image_rename/rename_by_shot_priority.py 放在一起（而不是留在 cfg/
下面），是因为这套改名脚本会被各品牌流水线大量调用，独立成一个 ops 子目录方便找。
cfg/brands/*.py 里通过绝对路径 `from ops.image_rename.image_priority_config import
IMAGE_PRIORITY_CONFIG` 引用这里的值——cfg 层反过来依赖 ops 层，是这个文件唯一的例外。

统一流程（所有品牌一致）：
  1. 各品牌流水线在生成 HTML 之前，对 IMAGE_PROCESS 目录跑一次
     rename_by_shot_priority(cfg["IMAGE_PROCESS"], brand="<brand>")，
     按 IMAGE_RENAME_PRIORITY 里的原始后缀顺序把文件改名为 {code}__1 / __2 / ...
     （命中的后缀排在前面，其余文件按文件名字母顺序追加在后面）。
  2. generate_html_from_codes_files / generate_first_page_from_codes_files
     分别按 IMAGE_DES_PRIORITY / IMAGE_FIRST_PRIORITY 里的数字索引，在改名后的
     {code}__N 序列里各自选一张封面图。两个列表通常故意配成不同顺序（比如
     FIRST=[1,2,3,...]、DES=[2,1,3,...]），这样首页和详情页不会选到同一张图；
     列表里排在前面的数字找不到文件时，会依次尝试后面的数字。

三个键：
- IMAGE_RENAME_PRIORITY：list[str]，rename_by_shot_priority 用来决定 {code}__N 的
  物理改名顺序。取值是各品牌原始下载图片真实使用的文件名后缀（不同供应商命名规则不同，
  换脸产出的 front_N_faceswap、字母视角后缀、2 位数字视角后缀等），照抄自各品牌原来的
  选图后缀列表，语义不变。
- IMAGE_FIRST_PRIORITY / IMAGE_DES_PRIORITY：list[int]，rename 之后按 {code}__N 里
  第 N 张选图，N 是该项在 IMAGE_RENAME_PRIORITY 里的位置（1-indexed）。
  具体选图逻辑见 common/publication/generate_html.py 的 find_image_path 和
  common/publication/generate_html_FristPage.py 的 find_image_url。

例外：
- geox 除了这一套（供 rename_by_shot_priority 改 IMAGE_PROCESS 用）之外，还单独有
  IMAGE_CUTTER_RENAME_ORDER（list[int]，供 brands/geox/helpers_local/rename_suffix.py
  改 IMAGE_CUTTER 用，上传 R2 / AI 视角旋转依赖这批文件严格是 {code}_1.jpg ~ _6.jpg
  这种固定 6 个槽位、单下划线的命名，不能改成 rename_by_shot_priority 那种按实际存在
  文件数量做的双下划线紧凑编号，两套改名机制不能合并）。
- camper 的 brands/camper/helpers_local/rename_suffix.py 改的是另一个目录
  （IMAGE_CUTTER，供上传 R2 / AI 视角旋转），复用同一份 IMAGE_RENAME_PRIORITY 数值
  没有冲突（都是原始字母后缀、按字符串精确匹配），所以不用单独拆键。
"""

IMAGE_PRIORITY_CONFIG = {
    "barbour": {
        # 改名脚本按这个顺序把换脸图排到最前面，其余图片按文件名字母顺序追加在后面
        "IMAGE_RENAME_PRIORITY": ["front_1_faceswap", "front_2_faceswap", "front_3_faceswap", "front_4_faceswap"],
        # 改名后 {code}__1 是换脸效果最好的一张，首页优先用它，不存在再依次退到 __2/__3/__4
        "IMAGE_FIRST_PRIORITY": [1, 2, 3, 4],
        # 详情页优先用第二张，避免和首页撞图；__2 不存在时退到 __1/__3/__4
        "IMAGE_DES_PRIORITY": [2, 1, 3, 4],
    },
    "camper": {
        # 同时供 brands/camper/helpers_local/rename_suffix.py（改 IMAGE_CUTTER）和
        # rename_by_shot_priority（改 IMAGE_PROCESS）两处使用，见文件头注释
        "IMAGE_RENAME_PRIORITY": ["F", "C", "L", "P", "T"],
        # 原始后缀 F/C/L/T 对应改名后的 __1/__2/__3/__5（跳过 P=__4，维持原有偏好）
        "IMAGE_FIRST_PRIORITY": [1, 2, 3, 5],
        # 原始后缀 C/F/L/T 对应 __2/__1/__3/__5
        "IMAGE_DES_PRIORITY": [2, 1, 3, 5],
    },
    "clarks": {
        # 供应商原始后缀固定是这个怪顺序（1,6,2,3,5,4,7,8,9），照抄自原来
        # brands/clarks/helpers_local/rename_suffix.py 的 SUFFIX_ORDER，
        # 按这个顺序改名后就等价于以前"图片重排"想要的 1,2,3,4,5,6,7,8,9 新编号。
        "IMAGE_RENAME_PRIORITY": ["1", "6", "2", "3", "5", "4", "7", "8", "9"],
        # 等价于新编号里的 1,2,6,3（原 IMAGE_FIRST_PRIORITY 就是按新编号写的）
        "IMAGE_FIRST_PRIORITY": [1, 2, 6, 3],
        # 原来 generate_html.py 对 clarks 有特殊逻辑：详情页封面固定取编号最大的文件。
        # 这里用完整倒序列表复现同样效果——9 不存在就退到 8，8 不存在再退到 7……
        "IMAGE_DES_PRIORITY": [9, 8, 7, 6, 5, 4, 3, 2, 1],
    },
    "ecco": {
        # 沿用原 DES 顺序作为改名基准（"2" 最优先）
        "IMAGE_RENAME_PRIORITY": ["2", "1", "3", "o", "s", "b"],
        # 原始后缀 1/2/3/o/s/b 对应改名后的 __2/__1/__3/__4/__5/__6
        "IMAGE_FIRST_PRIORITY": [2, 1, 3, 4, 5, 6],
        # 原始后缀 2/1/3/o/s/b 对应 __1/__2/__3/__4/__5/__6（就是改名顺序本身）
        "IMAGE_DES_PRIORITY": [1, 2, 3, 4, 5, 6],
    },
    "geox": {
        # 供 rename_by_shot_priority 改 IMAGE_PROCESS 用：字符串精确匹配文件名后缀，
        # 前两项 "07"/"01" 是原 FIRST/DES 里就有的补充视角，其余 6 个是官网固定视角
        # （00/10/30/50/60/40），"2" 是极少数解析失败时的兜底后缀（见
        # brands/geox/download_product_images.py 的 f"{idx}" 兜底）。
        "IMAGE_RENAME_PRIORITY": ["07", "00", "01", "10", "30", "50", "60", "40", "2"],
        # 原始后缀 07/00/01/2 对应改名后的 __1/__2/__3/__9
        "IMAGE_FIRST_PRIORITY": [1, 2, 3, 9],
        # 原始后缀 01/00/07/2 对应 __3/__2/__1/__9
        "IMAGE_DES_PRIORITY": [3, 2, 1, 9],
        # 单独给 brands/geox/helpers_local/rename_suffix.py 用（改 IMAGE_CUTTER，
        # 上传 R2 / AI 视角旋转依赖固定 6 槽位 + 单下划线命名，见文件头注释）
        "IMAGE_CUTTER_RENAME_ORDER": [0, 10, 30, 50, 60, 40],
    },
    "marksandspencer": {
        "IMAGE_RENAME_PRIORITY": ["front_1_faceswap", "front_2_faceswap"],
        # 原始后缀 front_1_faceswap/front_2_faceswap 对应 __1/__2
        "IMAGE_FIRST_PRIORITY": [1, 2],
        "IMAGE_DES_PRIORITY": [2, 1],
    },
    "reiss": {
        "IMAGE_RENAME_PRIORITY": ["s", "s2", "s3", "s4", "s5"],
        # 原始后缀 s/s3/s4 对应改名后的 __1/__3/__4
        "IMAGE_FIRST_PRIORITY": [1, 3, 4],
        # 原始后缀 s2/s3/s4/s5 对应 __2/__3/__4/__5（就是改名顺序本身）
        "IMAGE_DES_PRIORITY": [2, 3, 4, 5],
    },
}
