-- ========== 删除旧表（注意顺序：先删依赖表） ==========
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS barbour_products;
DROP TABLE IF EXISTS barbour_inventory;

-- ========== 表 1：产品表 products ==========
CREATE TABLE barbour_products (
    id SERIAL PRIMARY KEY,
    color_code VARCHAR(50) NOT NULL,          -- Barbour颜色编码，如 MWX0339NY91
    style_name VARCHAR(255) NOT NULL,         -- 款式名，如 Ashby Wax Jacket
    color VARCHAR(100) NOT NULL,              -- 颜色，如 Navy
    size VARCHAR(20) NOT NULL,                -- 尺码，如 M / UK 10 / XL

    gender VARCHAR(20),                       -- 性别：Men / Women / Kids
    category VARCHAR(100),                    -- 分类：Jacket / Coat / Shirt / Bag ...
    title VARCHAR(255),                       -- 标题（完整商品名，带品牌+款式+颜色）
    product_description TEXT,                 -- 商品描述（来自官网/站点）

    match_keywords TEXT[],                    -- 提取的关键词，用于匹配其他网站标题

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(color_code, size)                  -- 每个 SKU 唯一（颜色编码 + 尺码）
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

-- =========================
-- Barbour 发布表（与 clarks_jingya_inventory 对齐）
-- 仅新增 3 个选源字段：source_site / source_offer_url / source_price_gbp
-- =========================


CREATE TABLE barbour_inventory (
    id SERIAL PRIMARY KEY,

    -- 基础信息（保持与 clarks_jingya_inventory 一致）
    product_code VARCHAR(200) NOT NULL,      -- 这里写 Barbour 的 color_code，如 MWX0339NY91
    product_url  TEXT NOT NULL,              -- 选源链接（或你保留历史链接）
    size         VARCHAR(10) NOT NULL,       -- 尺码（S/M/L/XL 或 UK/INT）
    gender       VARCHAR(10),                -- 男款/女款/童款（可留空）

    -- 商品补充字段
    product_description TEXT,
    product_title       TEXT,
    style_category      VARCHAR(20),

    -- 淘宝&渠道绑定（完全沿用字段名，便于你现有代码复用）
    channel_product_id  VARCHAR(50),
    channel_item_id     VARCHAR(50),
    item_id             VARCHAR(50),
    skuid               VARCHAR(50),
    sku_name            VARCHAR(200),

    -- 库存与价格（沿用）
    ean                  VARCHAR(50),
    stock_count          INTEGER DEFAULT 0,
    original_price_gbp   NUMERIC(10, 2),
    discount_price_gbp   NUMERIC(10, 2),

    -- 状态控制（沿用）
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_published BOOLEAN DEFAULT FALSE,

    -- 仅为 Barbour 多供应商新增的 3 个“选源”字段（最小增量）
    source_site        VARCHAR(100),         -- 选中的站点（如 O&C / Allweathers / PMD 等）
    source_offer_url   TEXT,                 -- 选源 URL（可与 product_url 同步）
    source_price_gbp   NUMERIC(10, 2),       -- 选源英镑价（你的折算脚本用 discount_price_gbp 也可）

    -- 唯一约束：同一商品+尺码唯一（与 clarks 保持一致）
    UNIQUE (product_code, size)
);

-- 实用索引（一次建好即可）
CREATE INDEX IF NOT EXISTS idx_barbour_inv_sku   ON barbour_inventory(product_code, size);
CREATE INDEX IF NOT EXISTS idx_barbour_inv_item  ON barbour_inventory(item_id);
CREATE INDEX IF NOT EXISTS idx_barbour_inv_skuid ON barbour_inventory(skuid);
