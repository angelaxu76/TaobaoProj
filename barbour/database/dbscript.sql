-- ========== 删除旧表（注意顺序：先删依赖表） ==========
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS barbour_products;
DROP TABLE IF EXISTS barbour_inventory;

-- ========== 创建新表 ==========
CREATE TABLE barbour_products (
    id SERIAL PRIMARY KEY,

    -- Barbour 核心 SKU（商品编码 + 尺码）
    product_code VARCHAR(50) NOT NULL,          -- Barbour 商品编码，如 MWX0339NY91
    size VARCHAR(20) NOT NULL,                -- 尺码，如 M / UK 10 / XL

    -- 基础属性
    style_name VARCHAR(255) NOT NULL,         -- 款式名，如 Ashby Wax Jacket
    color VARCHAR(100) NOT NULL,              -- 颜色，如 Navy
    gender VARCHAR(20),                       -- 性别：Men / Women / Kids
    category VARCHAR(100),                    -- 分类：Jacket / Coat / Shirt / Bag ...
    title VARCHAR(255),                       -- 标题（完整商品名，带品牌+款式+颜色）
    product_description TEXT,                 -- 商品描述（来自官网/站点）
    match_keywords TEXT[],                    -- 提取的关键词，用于匹配其他网站标题

    -- 数据来源追踪
    source_site VARCHAR(100),                 -- 来源站点（barbour / O&C / PMD / manual）
    source_url TEXT,                          -- 来源链接
    source_rank INT DEFAULT 999,              -- 来源优先级：0=barbour官网,1=有编码站点,2=人工补码,999=未知

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 唯一约束：每个 SKU 唯一（编码 + 尺码）
    UNIQUE(product_code, size)
);

-- ========== 自动更新时间戳触发器 ==========
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_barbour_products_updated ON barbour_products;
CREATE TRIGGER trg_barbour_products_updated
BEFORE UPDATE ON barbour_products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ========== 表 2：库存价格表 offers ==========
-- 1) 表结构（product_code 允许为空）
DROP TABLE IF EXISTS barbour_offers CASCADE;

CREATE TABLE barbour_offers (
  id SERIAL PRIMARY KEY,

  -- 唯一识别：站点 + 链接 + 尺码
  site_name VARCHAR(100) NOT NULL,
  offer_url TEXT NOT NULL,
  size      VARCHAR(10) NOT NULL,

  -- 商品编码（可空；人工后续回填）
  product_code VARCHAR(50),

  -- 价格与库存
  price_gbp NUMERIC(10,2),
  original_price_gbp NUMERIC(10,2),
  stock_status VARCHAR(50),          -- '有货' / '无货' 或 'In Stock' / 'Out of Stock'
  can_order BOOLEAN DEFAULT FALSE,

  -- 维护字段
  is_active   BOOLEAN   DEFAULT TRUE,  -- 软删除/下架标记
  first_seen  TIMESTAMP DEFAULT NOW(),
  last_seen   TIMESTAMP DEFAULT NOW(),
  last_checked TIMESTAMP DEFAULT NOW(),

  UNIQUE (site_name, offer_url, size)
);

-- 可选索引



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
CREATE INDEX IF NOT EXISTS idx_bo_code   ON barbour_offers(product_code);
CREATE INDEX IF NOT EXISTS idx_bo_active ON barbour_offers(is_active);