-- ========== 删除旧表（注意顺序：先删依赖表） ==========
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS barbour_products;

-- ========== 表 1：产品表 products ==========
CREATE TABLE barbour_products (
    id SERIAL PRIMARY KEY,
    color_code VARCHAR(50) NOT NULL,         -- Barbour颜色编码，如 MWX0339NY91
    style_name VARCHAR(255) NOT NULL,        -- 款式名，如 Ashby Wax Jacket
    color VARCHAR(50) NOT NULL,              -- 颜色，如 Navy
    size VARCHAR(10) NOT NULL,               -- 尺码，如 M
    match_keywords TEXT[],                   -- 提取的关键词，用于匹配其他网站标题

    UNIQUE(color_code, size)                 -- 每个 SKU 唯一（颜色编码 + 尺码）
);

-- ========== 表 2：库存价格表 offers ==========
CREATE TABLE offers (
    id SERIAL PRIMARY KEY,
    color_code VARCHAR(50) NOT NULL,         -- 匹配产品 color_code
    size VARCHAR(10) NOT NULL,               -- 匹配产品尺码
    site_name VARCHAR(100) NOT NULL,         -- 站点名，如 Country Attire
    offer_url TEXT NOT NULL,                 -- 商品链接
    price_gbp NUMERIC(10, 2),                -- 当前价格
    stock_status VARCHAR(50),                -- 如 In Stock / Out of Stock
    can_order BOOLEAN DEFAULT FALSE,         -- 是否可下单
    last_checked TIMESTAMP DEFAULT NOW(),    -- 抓取时间

    UNIQUE(color_code, size, site_name)      -- 每个网站对同一 SKU 仅一条记录
);
