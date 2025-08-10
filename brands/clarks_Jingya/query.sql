


SELECT product_code,
       STRING_AGG(size, ', ' ORDER BY size) AS available_sizes,
       COUNT(*) AS available_count
FROM clarks_jingya_inventory
WHERE stock_count > 0
GROUP BY product_code
HAVING COUNT(*) >= 4;