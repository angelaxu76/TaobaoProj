


select * from barbour_products where style_name ILIKE '%beadnell%' and color ILIKE '%sage%'

select distinct color_code,style_name,color from barbour_products where style_name ILIKE '%beaufort%' and color_code ILIKE '%LQU0471%'


select distinct color_code,style_name,color from barbour_products where color_code ILIKE '%MWX0700%'

select * from ecco_inventory where product_code ='13090301007' and stock_name = '五小剑'


SELECT COUNT(*) AS need_update_count
FROM (
    SELECT product_code
    FROM ecco_inventory
    WHERE skuid IS NULL OR item_id IS NULL
    GROUP BY product_code
) t;

select count(*) AS need_update_count from

SELECT COUNT(*) AS record_count
FROM ecco_inventory
WHERE stock_name = '五小剑'
  AND skuid IS NOT NULL;



DROP TABLE IF EXISTS ecco_inventory;

CREATE TABLE ecco_inventory (
    id SERIAL PRIMARY KEY,
    product_code VARCHAR(200) NOT NULL,               -- 商品编码，如 206503-01001
    product_url TEXT NOT NULL,                        -- 商品页面 URL
    size VARCHAR(10) NOT NULL,                        -- 尺码，如 39, 40
    gender VARCHAR(10),                               -- 男款/女款
    item_id VARCHAR(50),							  -- 淘宝宝贝ID
    skuid VARCHAR(50),                                -- 淘宝 SKU ID（选填）
    stock_status VARCHAR(10) NOT NULL,                -- “有货” / “无货”
    original_price_gbp NUMERIC(10, 2),                -- 原价
    discount_price_gbp NUMERIC(10, 2),                -- 折扣价
    stock_name VARCHAR(100),                          -- 店铺名 / 店仓名
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后检测时间
    is_published BOOLEAN DEFAULT FALSE,               -- 是否发布到平台
    UNIQUE (product_code, size, stock_name)           -- 每个商品每个尺码每个店唯一
);