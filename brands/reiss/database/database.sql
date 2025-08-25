DROP TABLE IF EXISTS reiss_inventory;

CREATE TABLE reiss_inventory (
    id SERIAL PRIMARY KEY,

    -- 基础信息
    product_code VARCHAR(200) NOT NULL,               -- 商品编码
    product_url TEXT NOT NULL,                        -- 商品链接
    size VARCHAR(10) NOT NULL,                        -- 尺码
    gender VARCHAR(10),                               -- 性别：男款、女款、童款

    -- 商品补充字段
    product_description TEXT,                         -- 商品描述（来自 TXT）
    product_title TEXT,                               -- 商品标题（英文名称）
    style_category VARCHAR(20),                       -- 商品分类，如 coat、dress、shirt

    -- 淘宝&渠道绑定信息
    channel_product_id VARCHAR(50),                   -- 渠道产品 ID
    channel_item_id VARCHAR(50),                      -- 渠道货品 ID
    item_id VARCHAR(50),                              -- 淘宝宝贝ID
    skuid VARCHAR(50),                                -- 淘宝 SKU ID
    sku_name VARCHAR(200),                            -- SKU 规格名

    -- 库存与价格
    ean VARCHAR(50),                                  -- EAN 条码
    stock_count INTEGER DEFAULT 0,                    -- 实际库存数量
    original_price_gbp NUMERIC(10, 2),                -- 原价（GBP）
    discount_price_gbp NUMERIC(10, 2),                -- 折扣价（GBP）

    -- 状态控制
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后检查时间
    is_published BOOLEAN DEFAULT FALSE,               -- 是否已发布

    -- 店铺维度
    store_name VARCHAR(100),                          -- 店铺名（区分不同淘宝店）

    -- 唯一约束：同一商品+尺码+店铺 唯一
    UNIQUE (product_code, size, store_name)
);