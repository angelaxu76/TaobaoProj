"""
creative/ — 淘宝商品素材模块（文案，后续扩展短视频等）

creative/
├── product_source.py      商品资料读取（数据库 / TXT），各素材功能共用
├── store_items.py         渠道产品ID / 商品编码 → 各店淘宝商品ID
├── video/                 主图视频：图片 → 1:1 短视频，字幕用文案（见 creative/video/__init__.py）
└── copywriting/           商品文案：卖点1、卖点2、推荐理由、短标题、宝贝名称
    ├── naming.py          短标题 / 宝贝名称（规则生成：品牌 + 系列 + 商品名称）
    ├── series_names.py    系列英文名 → 中文名（配置 + AI 翻译，结果存 series_names.json 可手改）
    ├── safe_copy.py       卖点 / 推荐理由 保守模式（默认）：只用可核实事实 + 中性短语
    ├── selling_points.py  卖点 / 推荐理由 AI 模式：DeepSeek 生成 + 校验 + 事实核查
    ├── validator.py       字数、广告法、事实校验
    ├── service.py         按品牌批量生成
    ├── copy_excel.py      审核用 Excel：输出 / 读取之前的 Excel 复用
    ├── taobao_import.py   按淘宝「基础素材」导入模板，每店输出一个导入文件
    └── style_examples.txt 卖点风格参考（可直接增删，每行一条）

配置：cfg/creative_config.py    运行入口：ops/creative/

文案不入库，需要时生成 → Excel。（不放 {brand}_inventory：该表每次导入 TXT 都会 TRUNCATE，且一行是一个尺码。）
新功能新建子包（参照 creative/video/），用 product_source 取商品、copywriting.service.generate_for_brand 取文案、store_items 取淘宝商品ID。
"""
