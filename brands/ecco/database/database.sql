DROP TABLE IF EXISTS ecco_inventory;

CREATE TABLE ecco_inventory (
    id SERIAL PRIMARY KEY,
    product_code VARCHAR(200) NOT NULL,               -- 商品编码，如 206503-01001
    product_url TEXT NOT NULL,                        -- 商品页面 URL
    size VARCHAR(10) NOT NULL,                        -- 尺码，如 39, 40
    gender VARCHAR(10),                               -- 男款/女款
    item_id VARCHAR(50),                              -- 淘宝宝贝ID
    skuid VARCHAR(50),                                -- 淘宝 SKU ID
    stock_status VARCHAR(10) NOT NULL,                -- “有货” / “无货”
    stock_count INT DEFAULT 0,                        -- 库存数量（数值）
    original_price_gbp NUMERIC(10, 2),                -- 原价
    discount_price_gbp NUMERIC(10, 2),                -- 折扣价
    taobao_store_price NUMERIC(10, 2),                -- 淘宝售价
    stock_name VARCHAR(100),                          -- 店铺名 / 店仓名
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后检测时间
    is_published BOOLEAN DEFAULT FALSE,               -- 是否发布到平台
    UNIQUE (product_code, size, stock_name)           -- 每个商品 + 尺码 + 店铺唯一
);