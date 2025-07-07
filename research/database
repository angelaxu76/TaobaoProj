DROP TABLE IF EXISTS all_inventory;

CREATE TABLE all_inventory (
    id SERIAL PRIMARY KEY,

    item_id VARCHAR(50) UNIQUE,                            -- 淘宝宝贝ID
    product_code VARCHAR(200) NOT NULL,             -- 商品编码，如 206503-01001
    product_title VARCHAR(300) NOT NULL,            -- 商品标题
    price_gbp NUMERIC(10, 2),                       -- 商品价格（英镑）
    stock_name VARCHAR(100),                        -- 店铺名（如 五小剑）
    is_published BOOLEAN DEFAULT FALSE,             -- 是否发布

    -- 品牌、性别、类目与更新时间
    brand VARCHAR(50),                              -- 品牌名（如 clarks, camper 等）
    gender VARCHAR(20),                             -- 性别（男款 / 女款 / 中性）
    category VARCHAR(100),                          -- 类目（如 凉鞋 / 靴子 / 休闲鞋 等）
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后检测时间

    -- 店铺表现指标
    visitor_count INT,                              -- 商品访客数
    page_views INT,                                 -- 商品浏览量
    avg_stay_time_seconds INT,                      -- 平均停留时长（秒）
    favorite_count INT,                             -- 商品收藏人数
    cart_count INT,                                 -- 商品加购件数
    order_count INT,                                -- 下单件数
    order_conversion_rate NUMERIC(5, 2),            -- 下单转化率（百分比）
    search_visitors INT,                            -- 搜索引导访客数
    search_buyers INT                               -- 搜索引导支付买家数
);
