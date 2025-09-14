SELECT
  o.product_code,
  p.style_name AS product_style_name,   -- ✅ 用 style_name
  o.site_name,
  o.offer_url,
  MIN(o.price_gbp)::numeric(10,2)          AS price_gbp,
  MIN(o.original_price_gbp)::numeric(10,2) AS original_price,
  MAX(o.discount_pct)                      AS discount_pct,
  STRING_AGG(DISTINCT o.size, ',' ORDER BY o.size) AS sizes_in_stock,
  COUNT(DISTINCT o.size) FILTER (WHERE o.stock_count > 0) AS available_count
FROM barbour_offers o
LEFT JOIN barbour_products p
  ON o.product_code = p.product_code
WHERE o.product_code IS NOT NULL
  AND o.stock_count > 0
  AND o.discount_pct > 15
  AND o.product_code ILIKE '%MTS%'   -- ✅ 模糊过滤条件
GROUP BY o.product_code, p.style_name, o.site_name, o.offer_url
HAVING COUNT(DISTINCT o.size) > 3
ORDER BY discount_pct DESC, price_gbp ASC, o.product_code;



select * from barbour_offers  where product_code='LCA0352CR51' 
and site_name='barbour'
order by size;

select * from barbour_inventory 
where product_code='MCA1050OL11' ;

select * from barbour_offers  where site_name='outdoorandcountry' and product_code='MSP0145ST12' ;

select count(*) from barbour_offers  where original_price_gbp is null； 
   



