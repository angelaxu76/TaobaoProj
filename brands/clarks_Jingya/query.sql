

-- 查询每个商品编码至少有 4 个有货尺码
SELECT product_code,
       STRING_AGG(size, ', ' ORDER BY size) AS available_sizes,
       COUNT(*) AS available_count
FROM clarks_jingya_inventory
WHERE stock_count > 0
GROUP BY product_code
HAVING COUNT(*) >= 4;