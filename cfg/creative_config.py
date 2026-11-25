# cfg/creative_config.py
"""商品素材模块（creative/）配置：字数限制、商品名称词表、卖点事实校验规则。"""

# ── 字数限制 ───────────────────────────────────────────────────────────────────
# 空格也计入字数。
COPY_LIMITS = {
    "selling_point_1": 12,
    "selling_point_2": 12,
    "recommend_reason": 10,
    "short_title": 10,
    "item_name": 8,
}
# 一个英文字母/数字/空格算几个字。1 = 最严格（任何后台规则下都不会超）；
# 如果确认淘宝后台按"两个英文算一个字"，改成 0.5 可以保留更多英文系列名。
LATIN_CHAR_WEIGHT = 1

COPY_LABELS = {
    "selling_point_1": "卖点1",
    "selling_point_2": "卖点2",
    "recommend_reason": "推荐理由",
    "short_title": "短标题",
    "item_name": "宝贝名称",
}

# ── 短标题 / 宝贝名称里的品牌名（未列出的用 BRAND_NAME_MAP 的中文名，没有中文名用英文名）──
CREATIVE_BRAND_NAME = {}

# ── 商品名称：按顺序取第一个命中的（英文整词正则，不区分大小写）─────────────────
# 鞋类品牌：SMALL_ITEM → SHOE → ACCESSORY；服装品牌：SMALL_ITEM → ACCESSORY → CLOTHING → SHOE
# 先看标题（鞋类会先去掉系列名，避免 Camper "Runner" 系列被当成跑步鞋），再看 style_category。
SMALL_ITEM_RULES = [
    (r"(?:fast lock|shoe|boot) ?laces?", "鞋带"), (r"insoles?|inlay soles?", "鞋垫"),
    (r"shoe (?:care|cream)|cleaner|protector|shoe ?trees?", "鞋护理"),
    (r"backpacks?|rucksacks?", "双肩包"), (r"wallets?|purses?|card ?holders?", "钱包"),
    (r"bags?|tote|crossbody|handbags?|holdall|pouch", "包"), (r"socks?", "袜子"),
]
SHOE_RULES = [
    # 靴
    (r"snow boots?", "雪地靴"), (r"(?:wellington|welly|rain) ?boots?|wellingtons?|wellies", "雨靴"),
    (r"(?:hiking|trek(?:king)?|walking) boots?", "徒步靴"), (r"hiking shoes?", "徒步鞋"),
    (r"combat boots?|biker boots?", "马丁靴"),
    (r"chelsea", "切尔西靴"), (r"desert boots?", "沙漠靴"),
    (r"(?:knee[- ]high|high|long|tall) boots?", "长靴"),
    (r"ankle boots?|bootees?|booties?|boots?", "短靴"),
    # 凉鞋 / 拖鞋
    (r"flip[- ]?flops?", "人字拖"), (r"slides?", "拖鞋"), (r"mules?|clogs?", "穆勒鞋"),
    (r"slippers?", "拖鞋"), (r"sandals?|espadrilles?", "凉鞋"),
    # 皮鞋 / 女鞋
    (r"monk[- ]straps?", "孟克鞋"), (r"oxfords?", "牛津鞋"), (r"derby|derbys|derbies", "德比鞋"),
    (r"brogues?", "布洛克鞋"), (r"loafers?", "乐福鞋"), (r"moccasins?|moc[- ]toe", "莫卡辛"),
    (r"mary[- ]janes?(?:'s)?", "玛丽珍鞋"), (r"ballerinas?|ballet(?: flats?| pumps?)?", "芭蕾鞋"),
    (r"court shoes?|pumps?|stilettos?|high heels?|heels|heeled shoes?", "高跟鞋"),
    (r"boat shoes?|deck shoes?", "船鞋"),
    (r"dress shoes?|formal shoes?|formal|leather shoes?|trouser shoes?", "皮鞋"),
    # 运动 / 休闲
    (r"golf shoes?", "运动鞋"), (r"running shoes?", "跑步鞋"), (r"walking shoes?", "健步鞋"),
    (r"outdoor (?:waterproof )?shoes?|outdoor trainers?", "户外鞋"),
    (r"trainers?", "运动鞋"), (r"sneakers?|plimsolls?", "休闲鞋"),
    (r"slip[- ]?ons?|lace[- ]?ups?|shoes?|casual|wallabee", "休闲鞋"),
]
ACCESSORY_RULES = [
    (r"hats?|caps?|beanies?|sou'?wester|trapper|bakerboy", "帽子"), (r"scarf|scarves|snood|wrap", "围巾"),
    (r"gloves?|mittens?", "手套"), (r"umbrellas?", "雨伞"), (r"belts?", "腰带"),
    (r"earrings?|necklaces?|bracelets?|jewell?ery", "饰品"),
]
CLOTHING_RULES = [
    (r"gilets?|vests?|waistcoats?|body ?warmers?|liner", "马甲"),
    (r"wax(?:ed)? (?:[\w-]+ )?(?:jackets?|coats?)", "蜡棉夹克"),
    (r"quilt(?:ed)? (?:[\w'-]+ ){0,2}(?:jackets?|coats?)|polarquilt|liddesdale", "绗缝夹克"),
    (r"parkas?", "派克大衣"), (r"trench(?: coats?)?|macs?|raincoats?", "风衣"),
    (r"overshirts?", "衬衫外套"), (r"jackets?|bombers?|blazers?|anoraks?", "夹克"), (r"coats?|capes?", "大衣"),
    (r"hood(?:ie|ies|y)|sweatshirts?|half[- ]zip|quarter[- ]zip", "卫衣"), (r"fleece", "抓绒衣"),
    (r"cardigans?", "开衫"), (r"jumpers?|sweaters?|knitwear|knit|pullovers?|tanks?", "针织衫"),
    (r"polos?(?: shirts?)?", "POLO衫"), (r"t[- ]?shirts?|tees?", "T恤"), (r"dresses|dress(?! shirt)", "连衣裙"),
    (r"shirts?", "衬衫"), (r"blouses?|tops?", "上衣"), (r"pyjamas?|pajamas?|dressing gowns?|nightwear", "睡衣"),
    (r"jeans?", "牛仔裤"), (r"trousers?|chinos?|joggers?|leggings?|pants?", "长裤"), (r"shorts", "短裤"),
    (r"skirts?", "半身裙"), (r"jumpsuits?|dungarees?", "连体裤"), (r"swim\w*|bikinis?", "泳装"),
]
SHOE_BRANDS = {"camper", "clarks", "ecco", "geox", "birkenstock"}

# Barbour 标题识别不出时，按编码第 2~3 位判断（MWX → WX）
BARBOUR_PREFIX_CATEGORY = {
    "WX": "蜡棉夹克", "QU": "绗缝夹克", "GI": "马甲", "LI": "马甲", "SH": "衬衫", "KN": "针织衫", "TS": "T恤",
    "ML": "POLO衫", "CA": "夹克", "SP": "夹克", "WB": "夹克", "WO": "大衣", "OL": "卫衣", "TR": "长裤",
    "ST": "短裤", "DR": "连衣裙", "SK": "半身裙", "HA": "帽子", "SC": "围巾", "GL": "手套", "BA": "包",
    "RF": "雨靴", "FL": "凉鞋",
}

# 这些词被系列名提取误当成系列名时丢弃（颜色、性别、泛词）
SERIES_STOP_WORDS = {
    "系列", "camper", "clarks", "ecco", "geox", "barbour", "womens", "mens", "women", "men", "ladies", "the",
    "multicolor", "black", "white", "brown", "blue", "grey", "gray", "beige", "burgundy", "green", "red",
    "yellow", "orange", "pink", "purple", "navy", "gold", "silver", "other", "plus", "no", "c", "golf",
    "classic", "international", "new", "quilted", "waxed", "wax", "knitted", "tartan", "fleece", "cord", "shell",
    "mini", "sports", "summer", "cotton", "wool", "leather", "waterproof",
}

# 系列中文名（优先级最高；ECCO 另外会用 ECCO_SERIES_CN_MAP）。key 用大写。
# 这里没有的由 AI 翻译一次后存入 creative/copywriting/series_names.json，可直接改该文件，之后保持统一。
SERIES_CN_MAP = {
    "clarks": {"WALLABEE": "袋鼠", "DESERT": "沙漠"},
}

# ── 卖点事实校验 ───────────────────────────────────────────────────────────────
# 文案里出现左边的词，英文商品资料必须能匹配右边的正则，否则判为编造、打回重写。
FACT_RULES = [
    (r"防风|挡风|御风|风雨", r"wind|weather"),
    (r"全粒面|头层", r"full[- ]grain|top[- ]grain"),
    (r"整张|整皮", r"(?:single|one)[- ]piece|whole[- ]?cut|one piece"),
    (r"哑光", r"matte?\b"), (r"针织|织面", r"knit|woven|textile|fabric"), (r"排水", r"drain"),
    (r"双层|双密", r"double|dual|two"), (r"六片", r"six|6[- ]panel"), (r"气垫", r"\bair\b"),
    (r"抗菌|除臭|防臭", r"antibac|anti-bac|odou?r"), (r"恒温|控温", r"temperature|thermo"),
    (r"欧洲制造|欧洲产", r"made in (?:europe|the eu|spain|portugal|italy)"), (r"英国制造", r"made in (?:the uk|england|britain)"),
    (r"不累|久走|久穿|走一天|全天", r"cushion|shock|comfort|foam|ortholite|all[- ]day|support"),
    (r"磨脚", r"padded|seamless|friction|blister"), (r"好打理|易打理|易清洁", r"easy[- ]care|easy to clean|wipe|machine wash"),
    (r"蜡棉", r"wax"), (r"显瘦|显脚瘦|显腿", r"slim|flatter|elongat"),
    (r"透气|清爽|不闷|排汗|吸汗|干爽", r"breath|mesh|ventil|perforat|moisture|wick|airflow|linen|gore-?\s?tex"),
    (r"网面|网布", r"mesh"),
    (r"减震|缓震|缓冲", r"cushion|shock|absorb|foam|\beva\b|ortholite|rebound|phorene"),
    (r"轻盈|轻便|轻量|轻质|轻巧", r"light|\beva\b|weightless"),
    (r"防滑|抓地", r"slip[- ]resist|non[- ]?slip|anti[- ]?slip|grip|traction|\blug"),
    (r"耐磨|耐穿", r"durab|hard[- ]?wearing|abrasion|long[- ]lasting"),
    (r"柔软|软糯|软底", r"soft|supple|plush"),
    (r"弹力|弹性|回弹", r"elastic|stretch|rebound|respons|spring|energy"),
    (r"加绒|绒里|保暖|暖", r"warm|fleece|shearling|wool|insulat|thermal|cosy|cozy|\bfur\b|quilt|cashmere|merino"),
    (r"羊毛", r"\bwool|merino|lambswool|shearling"),
    (r"羊绒", r"cashmere"),
    (r"牛皮|真皮|头层|皮革|皮质|皮面", r"leather|calf|nubuck|suede|cow"),
    (r"小牛皮", r"calf"),
    (r"磨砂", r"nubuck|suede"),
    (r"麂皮|反绒|绒面|反毛", r"suede|nubuck"),
    (r"漆皮", r"patent"),
    (r"羊皮", r"lamb|sheep|goat|kid leather"),
    (r"记忆", r"memory"),
    (r"可拆|可换鞋垫", r"remov"),
    (r"宽楦|不挤脚", r"wide|room|extra width|generous"),
    (r"足弓", r"arch|anatom"),
    (r"一脚蹬|免系带|穿脱", r"slip[- ]?on|slip[- ]in|step in|easy[- ](?:on|in)|elastic|zip|on and off|quick|"
                          r"pull[- ]tab|buckle|strap"),
    (r"系带", r"lac(?:e|ing)"),
    (r"拉链", r"zip"),
    (r"厚底|增高|显高", r"platform|chunky|elevat|wedge|plateau|flatform"),
    (r"再生|环保|可持续", r"recycl|sustain|organic|responsib|leather working group|bio-based"),
    (r"手工|手作", r"hand[- ]?(?:made|craft|sewn|stitch|finish)"),
    (r"靴", r"\bboot"),
    (r"一字|拖", r"slide|sandal|mule|slipper|strap"),
    (r"棉", r"cotton|padded|quilt"),
    (r"亚麻", r"linen"),
]
# 防水分级（先剔除 WATER_IGNORE 里的局部/养护描述，再判断）：
#   waterproof = 整件防水；resistant = 防泼水/防小雨/蜡棉；none = 资料没写
# 原文出现 not waterproof 一律不算防水；同时写 waterproof 和 water resistant 时，除非有 WATER_STRONG 依据，否则按防泼水。
WATER_IGNORE = [
    r"waterproof[\s-]+(?:zips?|zippers?|pockets?|outsoles?|soles?|garment|spray|care)\b",
    r"(?:outsole|sole)\s+(?:that\s+|which\s+)?(?:guarantees?|ensures?|is)\s+(?:\w+\s+){0,3}waterproof\w*",
    r"(?:inhibit|restore|maintain|reproof)\w*\s+(?:the\s+|its\s+)?waterproof\w*", r"gore-?\s?tex[®™\s]+infinium",
]
WATER_NEGATED = r"(?:\bnot|n't|n’t|\bnon|\bnever)[\s-]+(?:\w+\s+){0,2}waterproof|waterproof\s*\?\s*no\b"
WATER_PROOF = r"waterproof|gore-?\s?tex|\bgtx\b|\babx\b|drytex|aquatex|\bwpf\b|ecco-tex"
WATER_STRONG = (r"gore-?\s?tex|\bgtx\b|\babx\b|drytex|aquatex|ecco-tex|membrane|"
                r"waterproof (?:construction|lining|upper|membrane|breathable)|fully waterproof")
WATER_RESIST = (r"water[- ]?(?:resist|repel)|shower|weather[- ]?(?:proof|resist)|[^a-z]wr[^a-z]|"
                r"wax(?:ed)? (?:cotton(?! lace)|jacket|coat|cap|hat|hood|flat|sports|storm)")
# 文案用词 → 需要的等级
WATER_CLAIM_RESIST = r"防泼水|泼水|拒水|疏水|抗水|小雨|阵雨|细雨"
WATER_CLAIM_PROOF = r"防水|雨|雪|隔水|阻水|挡水|防湿|不湿|怕湿|抗湿|防潮|隔潮|潮湿|水渍|浸水"
WATER_OVERCLAIM = r"无惧|不惧|不怕|无忧|不湿|不侵|大雨|暴雨|滴水不"     # 与水/雨/雪同时出现即为夸大

# 季节校验：文案词 → 不允许出现的商品名称
SEASON_CONFLICTS = [
    (r"夏|清凉|凉爽", {"短靴", "长靴", "雪地靴", "切尔西靴", "马丁靴", "徒步靴", "沙漠靴", "雨靴",
                     "围巾", "手套", "大衣", "绗缝夹克", "针织衫", "开衫"}),
    (r"冬|御寒|暖", {"凉鞋", "人字拖", "短裤", "泳装"}),
]
# 除广告法词库（common/text/ad_sanitizer.py）外，额外禁止的词
COPY_EXTRA_BANNED = ["正品", "代购", "包邮", "特价", "打折", "折扣", "清仓", "秒杀", "爆款", "最", "医", "治", "戈尔"]

# 推荐理由的侧重角度：每个商品按编码固定分配一个，避免全店都是"通勤百搭"
REASON_ANGLES = ["穿着体感", "材质工艺", "设计细节", "版型轮廓", "配色气质", "穿搭搭配", "适用场景", "风格个性"]


# ── 保守模式（creative/copywriting/safe_copy.py）─────────────────────────────────
# 材质：英文（整词，不区分大小写）→ 中文。只从英文标题和成分字段取（不从描述取，描述常写的是领口/饰边材质）。
SAFE_MATERIALS = [
    (r"patent", "漆皮"), (r"nubuck", "磨砂皮"), (r"suede|sde", "反绒皮"), (r"calf\s?skin|calf leather", "小牛皮"),
    (r"lamb\s?skin|nappa", "羊皮"), (r"waxed cotton|wax(?:ed)?", "蜡棉"), (r"cashmere", "羊绒"), (r"merino", "美利奴羊毛"),
    (r"wool", "羊毛"), (r"linen", "亚麻"), (r"corduroy|needlecord", "灯芯绒"), (r"denim", "牛仔布"),
    (r"canvas", "帆布"), (r"mesh", "网面"), (r"knit(?:ted)?", "针织"), (r"leather|lea", "皮革"),
    (r"textile|fabric", "织物"), (r"nylon|polyamide", "尼龙"), (r"polyester", "聚酯纤维"),
    (r"cotton", "棉质"), (r"synthetic", "合成材质"),
]
# 成分字段里主成分低于该比例时写「xx混纺」（只对面料类；皮革类直接不写）
SAFE_BLEND_THRESHOLD = 95
SAFE_BLEND_OK = {"羊绒", "美利奴羊毛", "羊毛", "亚麻", "棉质", "尼龙", "聚酯纤维", "织物"}
# 功能 / 穿法：(短语, 原文必须出现的英文, 是否只用于鞋)。按顺序最多取 2 个；防水另按 water_level 自动加在最前。
SAFE_FEATURES = [
    ("保暖内里", r"warm[- ]?lin|fleece[- ]lin|shearling lin|wool lin|fur lin|thermal lin|cosy lin|cozy lin", False),
    ("保暖设计", r"insulat|thermal", False),
    ("可拆鞋垫", r"(?<!non-)(?<!non )(?<!non)removable (?:\w+ )?(?:insole|footbed|inlay)", True),
    ("防滑鞋底", r"slip[- ]resist|non[- ]?slip|anti[- ]?slip", True),
    ("缓震设计", r"shock[- ]absorb|cushioning|cushioned (?:sole|outsole|midsole|footbed|insole|inlay)|zero shock", True),
    ("透气设计", r"breathab", False),
    ("轻便设计", r"lightweight|light-weight", False),
    ("拉链设计", r"full[- ]zip|zip[- ]?(?:fastening|closure|through|up)|side zip|zip front|front zip|two[- ]way zip|"
              r"lace and zip|zipped (?:front|closure)", False),
    ("弹力鞋带", r"elastic(?:ated)? lac", True),
    ("系带款式", r"lace[- ]?up|lace fastening", True),
    ("一脚蹬款", r"slip[- ]?on", True),
    ("魔术贴款", r"velcro|hook[- ]and[- ]loop|touch[- ]fasten", True),
    ("可拆连帽", r"detachable hood|removable hood", False),
    ("连帽设计", r"hooded|with (?:a )?hood|integrated hood", False),
]
# 防泼水：保守模式只认原文明确的说法（蜡棉的 weather-resistant 不算）
SAFE_WATER_RESIST = r"water[- ]?(?:resist|repel)|shower[- ]?proof"
# 凑字数用的中性短语（不涉及材质、性能、风格评价（简约/经典/复古）、身材效果）
SAFE_FILLERS = ["日常百搭", "出行实用"]
# 推荐理由：不含品类词（品牌标签不总可靠），不含「穿」（包、帽子也会用到）
SAFE_REASONS = ["日常百搭 出行实用", "日常出行 百搭之选", "百搭实用 日常可选", "日常出行都适用"]
