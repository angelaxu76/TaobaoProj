

-- 查询每个商品编码至少有 4 个有货尺码
SELECT product_code,
       STRING_AGG(size, ', ' ORDER BY size) AS available_sizes,
       COUNT(*) AS available_count
FROM clarks_jingya_inventory
WHERE stock_count > 0
GROUP BY product_code
HAVING COUNT(*) >= 4;

select * from clarks_jingya_inventory where channel_product_id = '969865905287'

select * from clarks_jingya_inventory where product_code = '26182835';

select * from clarks_jingya_inventory where channel_item_id = '970364276754'



WITH size_in_stock AS (
    SELECT
        product_code,
        COUNT(DISTINCT size) AS available_sizes,
        MAX(original_price_gbp) AS original_price_gbp,
        MAX(discount_price_gbp) AS discount_price_gbp
    FROM clarks_jingya_inventory
    WHERE stock_count > 0
    GROUP BY product_code
)
SELECT *
FROM size_in_stock
WHERE available_sizes > 4
  AND (original_price_gbp - discount_price_gbp) / original_price_gbp > 0.3;