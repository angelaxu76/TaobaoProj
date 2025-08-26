select * from reiss_inventory

select DISTINCT style_category from reiss_inventory

select DISTINCT product_code from reiss_inventory where style_category = 'Coats'

select * from reiss_inventory where product_code = 'F18-139'



WITH per_size AS (
  -- 同一商品若有多来源/多店铺，先按尺码聚合，取该尺码的最大库存
  SELECT
    product_code,
    LOWER(size) AS size_norm,
    MAX(stock_count) AS max_stock
  FROM reiss_inventory
  WHERE LOWER(style_category) = 'dress'
    AND LOWER(COALESCE(gender, '')) LIKE 'women%'
  GROUP BY product_code, LOWER(size)
)
SELECT
  product_code,
  COUNT(*) FILTER (WHERE max_stock > 0) AS in_stock_sizes,
  STRING_AGG(size_norm, ',' ORDER BY size_norm)
    FILTER (WHERE max_stock > 0)        AS sizes_in_stock
FROM per_size
GROUP BY product_code
HAVING COUNT(*) FILTER (WHERE max_stock > 0) > 2    -- 至少5个尺码有货
ORDER BY in_stock_sizes DESC, product_code;

select DISTINCT product_code from reiss_inventory where style_category IS NOT NULL



SELECT
    product_code,
    MIN(discount_price_gbp) AS discount_price_gbp,  -- 取最低折扣价
    COUNT(DISTINCT size) AS available_sizes
FROM reiss_inventory
WHERE stock_count > 0
GROUP BY product_code
HAVING COUNT(DISTINCT size) >= 3
ORDER BY product_code;

SELECT
    product_code,
    MAX(product_title) AS product_title,          -- 商品标题（取一个代表值）
    MAX(style_category) AS style_category,        -- 类别
    MIN(discount_price_gbp) AS discount_price_gbp,-- 最低折扣价
    COUNT(DISTINCT size) AS available_sizes,      -- 有货尺码数量
    SUM(stock_count) AS total_stock               -- 总库存
FROM reiss_inventory
WHERE stock_count > 0
GROUP BY product_code
HAVING COUNT(DISTINCT size) >= 3
ORDER BY discount_price_gbp ASC;      