# TaobaoProj — 项目说明（供 Claude 参考）

## 项目概述

英国品牌代购运营自动化系统。核心功能：
- 从英国各大供应商网站抓取商品信息（价格、库存、尺码）
- 写入本地 PostgreSQL 数据库
- 生成淘宝/精雅渠道所需的上架 Excel、价格 Excel、菜鸟绑货 Excel
- 生成商品详情 HTML 页面、淘宝标题

运营品牌：Barbour、Camper、Clarks（精雅渠道）、ECCO、GEOX、Birkenstock、REISS、Marks & Spencer

---

## 顶层目录结构

```
TaobaoProj/
├── cfg/            全局配置（路径、数据库、品牌参数、定价策略）
├── config.py       配置统一入口，从 cfg/ 聚合再导出
├── brands/         各品牌专属逻辑（抓取、数据库、发布流水线）
│   ├── barbour/
│   ├── camper/
│   ├── clarks_Jingya/
│   ├── ecco/
│   ├── geox/
│   ├── marksandspencer/
│   └── reiss/
├── channels/       销售渠道逻辑（淘宝、精雅）
│   ├── jingya/     精雅渠道（主力）
│   └── taobao/
├── common/         跨品牌/渠道的公共工具（见下方详细说明）
├── ops/            运营入口脚本（直接运行的 CLI）
│   ├── pricing/    价格相关操作
│   └── stock/      库存相关操作
├── analytics/      数据分析流水线
├── finance/        财务数据处理
├── helper/         底层工具脚本（图片处理/HTML转图/通用Excel工具）
├── research/       生意参谋数据研究
├── test/           测试脚本
└── _legacy/        旧代码存档（不维护）
```

---

## common/ 模块结构（2025-02 重构后）

原 `common/core/` 已按功能拆分到顶层子包，不再存在 `common/core/`。

```
common/
├── browser/        Chrome driver 与 Selenium 管理
│   ├── driver_auto.py      自动适配 Chrome 版本，构建 undetected_chromedriver
│   └── selenium_utils.py   共享 driver 池（get_driver / quit_driver）
├── image/          图片文件操作
│   ├── image_utils.py      copy_images_by_code()
│   ├── group_images_by_code.py
│   └── check_missing_images.py
├── ingest/         数据导入解析（完整版 TXT 解析）
│   ├── txt_parser.py       parse_txt_to_record() — 多品牌/多格式
│   └── txt_writer.py
├── maintenance/    维护工具
│   └── backup_and_clear.py
├── pricing/        价格计算与导出
│   ├── price_utils.py              calculate_discount_price() / calculate_jingya_prices()
│   └── export_discount_price.py    export_discount_excel()
├── product/        商品属性处理（类别/分类/尺码）
│   ├── category_utils.py   infer_style_category() — 从编码前缀推断类别
│   ├── classifier.py       SHOE_KEYWORDS 等关键词分类器
│   ├── size_normalizer.py  尺码归一化
│   └── size_utils.py       clean_size_for_barbour()
├── publication/    发布 HTML 生成
│   ├── generate_html.py
│   ├── generate_html_FristPage.py
│   └── generate_html_noImage.py
├── stock/          库存数据导出
│   └── export_store_stock.py   export_store_stock_excel()
├── text/           文本生成与处理
│   ├── ad_sanitizer.py                     sanitize_text() / sanitize_features()
│   ├── translate.py                        safe_translate() — 腾讯云翻译
│   ├── generate_taobao_title.py            最新版标题生成入口
│   ├── generate_taobao_title_v1.py
│   ├── generate_taobao_title_apparel.py    服装类标题生成
│   ├── generate_taobao_title_outerwear.py  外套类标题生成
│   └── style_extractors.py
└── utils/          通用小工具
    ├── logger_utils.py     setup_logger()
    └── txt_parser.py       extract_product_info() — 简版字段提取
```

**import 规范示例：**
```python
from common.browser.selenium_utils import get_driver, quit_driver
from common.pricing.price_utils import calculate_jingya_prices
from common.product.size_utils import clean_size_for_barbour
from common.product.category_utils import infer_style_category
from common.text.translate import safe_translate
from common.text.ad_sanitizer import sanitize_text
from common.utils.logger_utils import setup_logger
from common.image.image_utils import copy_images_by_code
from common.utils.txt_parser import extract_product_info   # 简版
from common.ingest.txt_parser import parse_txt_to_record   # 完整版（多品牌）
```

---

## 配置体系（cfg/）

```
cfg/
├── settings.py         API_KEYS、SETTINGS（汇率/库存模式）、GLOBAL_CHROMEDRIVER_PATH
├── db_config.py        PGSQL_CONFIG（PostgreSQL 192.168.1.44）、BRAND_TABLE 映射
├── paths.py            BASE_DIR、DISCOUNT_EXCEL_DIR、ensure_all_dirs()
├── brand_config.py     BRAND_CONFIG — 各品牌路径/参数字典
├── brand_strategy.py   TAOBAO_STORES、BRAND_STRATEGY、BRAND_NAME_MAP、BRAND_DISCOUNT
├── publish_config.py   EXCEL_CONSTANTS_BASE/BY_BRAND、PUBLISH_RULES
├── size_ranges.py      SIZE_RANGE_CONFIG
├── brands/             各品牌专属配置文件
└── taobao_title_keyword_config.py  标题关键词配置
```

**使用方式：** 统一从 `config.py` 导入，不直接导 `cfg.*`（除非在 common/ 内部）：
```python
from config import BRAND_CONFIG, BRAND_NAME_MAP, PGSQL_CONFIG
```

---

## 数据库

- PostgreSQL，host: `192.168.1.44:5432`，dbname: `taobao_inventory_db`（当前 active）
- 各品牌独立表：`camper_inventory`、`barbour_inventory`、`clarks_jingya_inventory` 等
- 连接通过 `psycopg2`，配置见 `cfg/db_config.py`

---

## 品牌/渠道内部结构模式

每个品牌目录下通常包含：
- `supplier/`：各供应商抓取脚本（`*_fetch_info.py`、`*_get_links.py`）
- `database/`：DB 读写操作
- `pipeline/`：完整自动化流水线（抓取 → 入库 → 导出）
- `core/`：品牌专属工具（Barbour 有较多 core 文件）
- `legacy/`：旧脚本存档

精雅渠道（`channels/jingya/`）按操作类型分：
- `ingest/`：导入 TXT/Excel 到数据库
- `export/`：生成各类 Excel（发布、价格、SKU、宝贝ID）
- `pricing/`：定价策略、折扣计算、折扣候选商品导出
- `check/`：价格校验、鲸芽数据解析、商家编码重复检查
- `cainiao/`：菜鸟仓储绑货相关
- `maintenance/`：库存维护、下架操作

---

## 运营入口（ops/）

直接运行的 CLI 脚本，修改文件内的参数后执行：

| 脚本 | 用途 |
|------|------|
| `ops/stock/run_zero_stock_offline.py` | 将指定商品编码的库存设为 0（下架） |
| `ops/stock/run_clean_low_stock.py` | 清理低库存商品 |
| `ops/pricing/run_pricing_validate.py` | 校验定价合规性 |

---

## helper/ 与 channels/ 的边界

`helper/` 只放**底层工具**，不含业务逻辑：
- `helper/image/`：图片格式转换、裁剪、水印、反指纹等 — 被多个品牌 pipeline import，**不要移动**
- `helper/html/`：HTML → PNG 转换（Firefox/Selenium）— 同上，被品牌 pipeline import
- `helper/excel/`：仅保留纯通用工具（`split_excel_by_rows.py` 等）
- `helper/txt/`：adhoc 文本处理（硬编码路径，一次性用）

**业务相关的 Excel 脚本已归入渠道目录**（2025-02 整理）：
| 原位置 | 新位置 |
|--------|--------|
| `helper/excel/export_discount_candidates_excel.py` | `channels/jingya/pricing/` |
| `helper/excel/get_taobao_ids_from_discount_list.py` | `channels/jingya/pricing/` |
| `helper/excel/export_excel_from_jingya_copy.py` | `channels/jingya/check/parse_jingya_copy_to_excel.py` |
| `helper/excel/find_duplicate_codes_excel.py` | `channels/jingya/check/find_duplicate_item_id_codes.py` |
| `helper/excel/export_tb_item_ids_from_productCode.py` | `channels/jingya/export/export_item_ids_by_code.py` |

---

## 关键约定

- Python 3.13，Windows 11，ChromeDriver 路径：`D:\chromedriver\chromedriver.exe`
- 汇率固定在 `cfg/settings.py`（EXCHANGE_RATE = 9.7），不要硬编码
- `_legacy/` 和 `*/legacy/` 目录内的脚本**不维护**，只做参考
- 品牌 key 统一小写：`"barbour"`, `"camper"`, `"clarks_jingya"`, `"ecco"`, `"geox"`
- 所有 TXT 商品文件编码为 UTF-8
- 新增业务脚本优先放 `channels/jingya/` 对应子目录或 `ops/`，不放 `helper/`
