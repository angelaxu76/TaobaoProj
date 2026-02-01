# taobao_title_keyword_config.py
# 所有词表/映射/规则集中在这里（可维护的冒号逗号风格）

# -------------------------
# 基础颜色映射（你原来的 그대로搬过来）
# -------------------------
COLOR_MAP = {
    "black": "黑色", "white": "白色", "red": "红色", "navy": "深蓝色", "tan": "浅棕色",
    "brown": "棕色", "blue": "蓝色", "grey": "灰色", "gray": "灰色", "green": "绿色", "olive": "橄榄绿",
    "pink": "粉色", "burgundy": "酒红色", "beige": "米色", "cream": "奶油色",
    "silver": "银色", "gold": "金色", "stone": "石灰色", "orange": "橙色",
    "plum": "梅子色", "taupe": "灰褐色", "cola": "可乐色", "off white": "米白色",
    "pewter": "锡色", "rust": "铁锈红", "light tan": "浅棕褐", "dark tan": "深棕褐",
    # —— 新增更常见色名与组合 —— #
    "dark brown": "深棕色", "mid brown": "中棕色", "light brown": "浅棕色",
    "dark blue": "深蓝色", "light blue": "浅蓝色", "sky blue": "天蓝色", "denim": "牛仔蓝",
    "charcoal": "炭灰色", "khaki": "卡其色", "camel": "驼色", "sand": "沙色", "cognac": "干邑棕",
    "ivory": "象牙白", "cream white": "奶油白", "off-white": "米白色", "multicolor": "多色", "multi": "多色"
}

COLOR_KEYWORDS = [
    "black", "tan", "navy", "brown", "white", "grey", "gray", "off white", "blue",
    "silver", "olive", "cream", "red", "green", "beige", "cola", "pink",
    "burgundy", "taupe", "stone", "bronze", "orange", "walnut", "pewter",
    "plum", "yellow", "rust", "khaki", "camel", "charcoal", "cognac", "sand", "multi"
]

COLOR_GUESS = {
    "black": "黑色", "white": "白色", "off white": "米白色", "ecru": "米色",
    "brown": "棕色", "tan": "棕色", "navy": "深蓝色", "blue": "蓝色", "green": "绿色",
    "red": "红色", "beige": "米色", "grey": "灰色", "gray": "灰色", "charcoal": "炭灰色",
    "khaki": "卡其色", "camel": "驼色", "cognac": "干邑棕", "sand": "沙色"
}


# -------------------------
# 材质映射（标题里“主材质”）
# -------------------------
MATERIAL_CANON_MAP = {
    "小牛皮": ["calfskin", "calf skin"],
    "头层牛皮": ["full grain", "full-grain"],
    "漆皮": ["patent leather", "patent"],
    "磨砂皮": ["nubuck"],
    "反毛皮": ["suede"],
    "牛皮": ["leather", "genuine leather"],
    "网布": ["mesh"],
    "织物": ["textile", "fabric"],
    "帆布": ["canvas"],
    "合成材质": ["synthetic"]
}

# 用于清理英文残留（可选：把英文词替换成中文）
TERM_REPLACE_MAP = {
    "防泼水": ["water resistant", "water-resistant"],
    "防水": ["waterproof", "gore tex", "gore-tex", "goretex", "gtx", "abx"],
    "头层牛皮": ["full grain", "full-grain"],
    "真皮": ["genuine leather"],
    "漆皮": ["patent leather"],
    "牛皮": ["leather"],
    "磨砂皮": ["nubuck"],
    "反毛皮": ["suede"],
    "织物": ["textile"],
    "网布": ["mesh"],
    "帆布": ["canvas"],
    "合成材质": ["synthetic"]
}

# -------------------------
# 鞋型（只选 1 个）：用“中文: [英文同义词...]”
# 说明：字典本身无序（py3.7+保持插入顺序），你按“优先级从高到低”写就行
# -------------------------
SHOE_TYPE_MAP = {
    # 靴类优先（你可按业务调整顺序）
    "雪地靴": ["snow boot", "snow boots"],
    "冬靴": ["winter boot", "winter boots"],
    "徒步靴": ["hiking boot", "hiking boots", "trek boot", "trek boots"],
    "马丁靴": ["combat boot", "combat boots"],
    "切尔西靴": ["chelsea"],
    "裸靴": ["ankle boot", "ankle boots", "bootie", "booties"],
    "系带靴": ["lace up boot", "lace-up boot", "lace up boots", "lace-up boots"],
    "短靴": ["boot", "boots"],

    # 皮鞋/乐福
    "孟克鞋": ["monk strap", "monk-strap"],
    "牛津鞋": ["oxford", "oxfords"],
    "德比鞋": ["derby", "derbys"],
    "布洛克鞋": ["brogue", "brogues"],
    "莫卡辛": ["moccasin", "moccasins", "moc"],
    "乐福鞋": ["loafer", "loafers", "penny loafer", "tassel loafer"],

    # 运动/休闲
    "跑步鞋": ["running shoe", "running shoes", "runner", "runners"],
    "健步鞋": ["walking shoe", "walking shoes"],
    "运动鞋": ["trainer", "trainers", "sport shoe", "sport shoes"],
    "休闲鞋": ["sneaker", "sneakers", "casual shoe", "casual shoes"],
    "板鞋": ["court shoe", "court shoes"],

    # 凉鞋/拖鞋
    "穆勒鞋": ["mule", "mules"],
    "一字拖": ["slide", "slides"],
    "人字拖": ["flip flop", "flip-flop", "flip flops", "flip-flops"],
    "拖鞋": ["slipper", "slippers"],
    "凉鞋": ["sandal", "sandals"],

    # 女鞋补充（可选）
    "芭蕾鞋": ["ballet", "ballet flat", "ballet flats"],
    "高跟鞋": ["pump", "pumps", "heel", "heels", "wedge", "wedges", "court"],
}

# -------------------------
# 功能特性（可多选）：中文 -> 同义词
# 你可以持续加词，不用写正则
# -------------------------
FEATURE_MAP = {
    "防水": ["waterproof", "gore tex", "gore-tex", "goretex", "gtx", "abx", "drytex", "aquatex"],
    "防泼水": ["water resistant", "water-resistant"],
    "透气": ["breathable", "mesh lining", "moisture wicking", "moisture-wicking"],
    "加绒": ["warm lined", "cosy lining", "cozy lining", "fleece lined", "fur lined"],
    "保暖": ["insulated", "thermal"],
    "防滑": ["non slip", "non-slip", "slip resistant", "slip-resistant", "grip", "traction", "mimic grip"],
    "橡胶底": ["rubber outsole", "rubber sole"],
    "轻盈": ["lightweight"],
    "缓震": ["cushioned", "cushioning"],
    "减震": ["shock absorbing", "shock-absorbing"],
    "记忆鞋垫": ["memory foam"],
    "可拆鞋垫": ["removable insole", "removable footbed"],
    "足弓支撑": ["arch support"],
    "一脚蹬": ["slip on", "slip-on"],
    "系带": ["lace up", "lace-up"],
    "拉链": ["zip", "zipped"],
    "魔术贴": ["velcro"],
    "宽楦": ["wide fit", "wide-width", "wide width", "wide"],
}

# 特性合并：命中这两个/多个后，替换成一个（省字节更自然）
FEATURE_MERGE_RULES = [
    ({"加绒", "保暖"}, "加绒保暖"),
]

# 特性排序：强制某些词更靠前（比如“防水”极重要）
FEATURE_FORCE_FIRST = ["防水"]

# 每个标题最多保留多少个特性词
MAX_FEATURES = 3

# -------------------------
# 品牌差异（v1 只放“短码规则”和“是否加短码”）
# -------------------------
BRAND_SHORT_CODE_RULE = {
    "ecco": {"mode": "ecco_6", "enable": True},
    "camper": {"mode": "style", "enable": True},
    "clarks_jingya": {"mode": "style", "enable": True},
    "default": {"mode": "style", "enable": False},
}

# 短码拼接是否加空格（你之前也在纠结空格；这里开关统一控制）
SHORT_CODE_JOIN_WITH_SPACE = True

# -------------------------
# 不足 60 字节补齐用（你也可以后续把“补齐词”改成由关键词触发而不是随机）
# -------------------------
FILLER_WORDS = [
    "新款", "百搭", "舒适", "潮流",  "时尚", "复古",
    "透气", "柔软", "减震", "轻盈", "耐穿", "通勤", "日常", 
]


MAX_SHOE_TYPES = 2  # 同时命中多个鞋型时，最多输出2个
