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



select * from barbour_offers  where product_code='MCA1050OL11' 
and site_name='barbour'
order by size;

select *
from barbour_inventory
where product_code = 'MSP0145ST12';

select * from barbour_offers  where site_name='outdoorandcountry' and product_code='MSP0145ST12' ;

select count(*) from barbour_offers  where original_price_gbp is null； 
   
WITH inv AS (
  SELECT
    size AS inv_size,
    lower(                                   -- 统一成小写
      regexp_replace(
        regexp_replace(size,
                       '^uk[[:space:]]*',    -- 去掉前缀 UK + 后续空白
                       '',
                       'i'                   -- i: 不区分大小写
        ),
        '[[:space:]\./-]+',                  -- 去：空白、点、斜杠、连字符
        '',
        'g'                                  -- g: 全局
      )
    ) AS inv_norm
  FROM barbour_inventory
  WHERE lower(product_code) = lower('MCA1050OL11')
)
SELECT DISTINCT inv_size, inv_norm FROM inv;



  last_checked DESC;

   


  select distinct product_code from barbour_inventory where product_code ilike '%LQU%' order by product_code;


  select  distinct product_code from barbour_offers where product_code ilike '%LQU%' ORDER BY product_code;


  select * from barbour_inventory where product_code='LCA0365OL51';

  select * from barbour_inventory 
  where channel_product_id='977341087977'