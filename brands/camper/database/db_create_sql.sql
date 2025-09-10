DROP TABLE IF EXISTS camper_inventory;

CREATE TABLE camper_inventory (
    id SERIAL PRIMARY KEY,

    -- 基础信息
    product_code VARCHAR(200) NOT NULL,               -- 商品编码，如 K800548-001
    product_url TEXT NOT NULL,                        -- 商品链接
    size VARCHAR(10) NOT NULL,                        -- 尺码（EU，如 38、39）
    gender VARCHAR(10),                               -- 性别：男款、女款、童款

    -- 商品补充字段
    product_description TEXT,                         -- 商品描述（用于识别鞋款/生成名称等）
    product_title TEXT,                               -- 商品标题（如英文名称）
    style_category VARCHAR(20),                       -- 鞋款分类，如 boots、sandal、casual 等

    -- 淘宝&渠道绑定信息（用于淘经销对接）
    channel_product_id VARCHAR(50),                   -- 渠道产品 ID（整个商品）
    channel_item_id VARCHAR(50),                      -- 渠道货品 ID（SKU 对应）
    item_id VARCHAR(50),                              -- 淘宝宝贝ID
    skuid VARCHAR(50),                                -- 淘宝 SKU ID
    sku_name VARCHAR(200),                            -- SKU 规格名，如 黑色42码

    -- 库存与价格
    ean VARCHAR(50),                                  -- EAN 条码
    stock_count INTEGER DEFAULT 0,                    -- 实际库存数量
    original_price_gbp NUMERIC(10, 2),                -- 原价（单位 GBP）
    discount_price_gbp NUMERIC(10, 2),                -- 折扣价（单位 GBP）

    -- 状态控制
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后检查时间
    is_published BOOLEAN DEFAULT FALSE,               -- 是否已发布（平台上架状态）

    -- 唯一约束：同一商品+尺码唯一
    UNIQUE (product_code, size)
);
