DROP TABLE IF EXISTS catalog_items;

CREATE TABLE catalog_items (
    id SERIAL PRIMARY KEY,

    -- 商品唯一业务主键
    product_code   VARCHAR(64),    -- 商品编码（跨链接唯一）
    item_name      TEXT,            -- 商品名称

    -- 基础属性
    brand          VARCHAR(64),
    category       VARCHAR(64),

    publication_date date,
    -- 定价
    list_price     NUMERIC(12,2),            -- 一口价（标价）

    -- 当前在售链接（可为空）
    current_item_id BIGINT,

    -- 商品状态
    status         VARCHAR(32) DEFAULT 'active',
    -- active / deleted / sold_out / archived

    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP INDEX IF EXISTS idx_catalog_items_product_code;

CREATE INDEX IF NOT EXISTS idx_catalog_items_product_code
ON catalog_items (product_code)
WHERE product_code IS NOT NULL;





-- ===============================
-- 1. 删除旧表（如存在）
-- ===============================
DROP TABLE IF EXISTS product_metrics_daily CASCADE;


-- ===============================
-- 2. 创建新表（定版 schema）
-- ===============================
CREATE TABLE product_metrics_daily (
  stat_date date NOT NULL,
  item_id bigint NOT NULL,          -- 宝贝ID，用于 join catalog_items
  store_name text NOT NULL,         -- 店铺名（多店铺）

  -- ===== 成交结果 =====
  pay_amount numeric(18,2),
  pay_qty integer,
  pay_buyer_cnt integer,
  refund_amount numeric(18,2),

  -- ===== 行为漏斗 =====
  cart_qty integer,
  cart_buyer_cnt integer,
  visitors integer,
  pageviews integer,
  pay_cvr numeric(10,6),

  -- ===== 价值指标 =====
  aov numeric(18,2),
  old_buyer_cnt integer,
  fav_cnt integer,
  uv_value numeric(18,2),

  -- ===== 流量拆分 =====
  platform_visitors integer,
  platform_visitors_share numeric(10,6),

  search_visitors integer,
  search_cart_buyer_cnt integer,
  search_pay_amount numeric(18,2),
  search_pay_qty integer,
  search_pay_buyer_cnt integer,

  recommend_visitors integer,
  recommend_cart_buyer_cnt integer,
  recommend_pay_amount numeric(18,2),
  recommend_pay_qty integer,

  kwpromo_visitors integer,
  kwpromo_cart_buyer_cnt integer,
  kwpromo_pay_amount numeric(18,2),
  kwpromo_pay_buyer_cnt integer,

  -- ===== 扩展字段 =====
  raw_metrics jsonb,

  imported_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT product_metrics_daily_pk
    PRIMARY KEY (stat_date, item_id, store_name)
);


-- ===============================
-- 3. 索引（只加“值回票价”的）
-- ===============================

-- 商品趋势 / join catalog_items
CREATE INDEX idx_pmd_item_date
ON product_metrics_daily (item_id, stat_date);

-- 店铺维度汇总
CREATE INDEX idx_pmd_store_date
ON product_metrics_daily (store_name, stat_date);

-- （可选）Top 商品榜
-- CREATE INDEX idx_pmd_date_pay_amount
-- ON product_metrics_daily (stat_date, pay_amount DESC);
