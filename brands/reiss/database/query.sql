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