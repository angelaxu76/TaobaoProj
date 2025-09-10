


select * from barbour_products where style_name ILIKE '%beadnell%' and color ILIKE '%sage%';

select distinct product_code,style_name,color
from barbour_products where style_name ILIKE '%beadnell%' and product_code ILIKE '%LQU0471%';


select distinct product_code,style_name,color from barbour_products where product_code ILIKE '%LWX0667NY91%';

select * from ecco_inventory where product_code ='13090301007' and stock_name = '五小剑';


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

select COUNT(*) from barbour_offers where site_name = 'Barbour';

select COUNT(*) from barbour_products;

select * from offers where site_name = 'Barbour';

select * from barbour_products where product_code ILIKE '%LQU1776%';


select count(*) from barbour_products;

select * from barbour_offers;


WITH sku_sizes AS (
  SELECT product_code, COUNT(*) AS total_sizes
  FROM barbour_products
  GROUP BY product_code
),
site_coverage AS (
  SELECT
    o.product_code,
    o.site_name,
    COUNT(DISTINCT o.size) AS available_sizes
  FROM offers o
  JOIN barbour_products p
  WHERE
    o.can_order = TRUE
    AND (
      o.stock_status IS NULL
      OR o.stock_status ILIKE 'in stock'
      OR o.stock_status = '有货'
    )
  GROUP BY o.product_code, o.site_name
),
full_sites AS (
  SELECT sc.product_code, sc.site_name
  FROM site_coverage sc
  JOIN sku_sizes s USING (product_code)
  WHERE sc.available_sizes = s.total_sizes
),
qualified AS (
  SELECT product_code, COUNT(DISTINCT site_name) AS site_count
  FROM full_sites
  GROUP BY product_code
  HAVING COUNT(DISTINCT site_name) >= 2
)
SELECT
  q.product_code,
  MIN(p.style_name) AS style_name,
  ARRAY_AGG(DISTINCT p.size ORDER BY p.size) AS all_sizes,
  ARRAY_AGG(DISTINCT f.site_name ORDER BY f.site_name) AS full_sites,
  MAX(q.site_count) AS site_count         -- ← 加出来
FROM qualified q
JOIN barbour_products p USING (product_code)
JOIN full_sites f USING (product_code)
GROUP BY q.product_code
ORDER BY site_count DESC, q.product_code;    -- ← 用上面的别名排序



SELECT DISTINCT color
FROM barbour_products
WHERE lower(color) LIKE '%empire%';




WITH sku_sizes AS (
  SELECT product_code, COUNT(*) AS total_sizes
  FROM barbour_products
  GROUP BY product_code
),
site_coverage AS (
  SELECT
    o.product_code,
    o.site_name,
    COUNT(DISTINCT o.size) AS available_sizes
  FROM offers o
  JOIN barbour_products p
    ON p.product_code = o.product_code AND p.size = o.size
  WHERE
    o.can_order = TRUE
    AND (
      o.stock_status IS NULL
      OR o.stock_status ILIKE 'in stock'
      OR o.stock_status = '有货'
    )
  GROUP BY o.product_code, o.site_name
),
full_sites AS (
  SELECT sc.product_code, sc.site_name
  FROM site_coverage sc
  JOIN sku_sizes s USING (product_code)
  WHERE sc.available_sizes = s.total_sizes
),
qualified AS (
  SELECT product_code, COUNT(DISTINCT site_name) AS site_count
  FROM full_sites
  GROUP BY product_code
  HAVING COUNT(DISTINCT site_name) >= 2
)
SELECT
  q.product_code,
  MIN(p.style_name) AS style_name,
  ARRAY_AGG(DISTINCT p.size ORDER BY p.size) AS all_sizes,
  ARRAY_AGG(DISTINCT f.site_name ORDER BY f.site_name) AS full_sites,
  MAX(q.site_count) AS site_count
FROM qualified q
JOIN barbour_products p USING (product_code)
JOIN full_sites f USING (product_code)
WHERE q.product_code LIKE 'MQU%'    -- ✅ 只要 MCA 开头的 color_code
GROUP BY q.product_code
ORDER BY site_count DESC, q.product_code;



select distinct product_code from barbour_inventory

select count(*) from barbour_offers;

select * from barbour_inventory;

select count(*) from barbour_products;

select * from barbour_inventory where product_code ILIKE '%LWX1492%';

select * from barbour_inventory where product_code = 'MSH5691BK11';
;
select * from barbour_products where product_code = 'MQU1872BK11';

select * from barbour_products where style_name ILIKE '%Aldon%';

select * from barbour_products where style_name ILIKE '%beadnell%'

select * from barbour_offers where product_code = 'LWX0667SG91';

select count(*) from barbour_offers

select * from barbour_supplier_map

select * from barbour_offers where site_name = 'houseoffraser'

SELECT site_name, size, stock_status, can_order
FROM offers
WHERE product_code = 'MCA1051NY71'
ORDER BY site_name, size;

select * from barbour_products where style_name ILIKE '%bedale%';

select * from barbour_products where product_code ILIKE '%LSP0220%';

select * from offers where product_code ILIKE '%LSP0220%';

SELECT distinct product_code
FROM barbour_products
WHERE product_code LIKE ANY (ARRAY[
  'LWX0003%', 'LWX1414%', 'LWX1411%', 'LWX1410%', 'LWX1404%', 'LWX1482%',
  'LWX1412%', 'LWX1470%', 'LWX1402%', 'LWX1497%', 'LWX1483%', 'LWX0534%',
  'LWX1493%', 'LWX1515%', 'LWX1495%', 'LWX1498%',
  'LQU1815%', 'LQU1825%', 'LQU1821%', 'LQU1820%', 'LQU1813%', 'LQS0058%',
  'LQU1836%', 'LQU1824%', 'LQU1833%', 'LQU1837%', 'LQU1844%', 'LQU1856%',
  'LQU1839%', 'LQU1840%', 'LQU1852%', 'LQU1851%',
  'LCA0358%', 'LCA0362%', 'LCA0365%', 'LCA0366%', 'LCA0367%', 'LCA0370%',
  'LCA0353%', 'LCA0354%', 'LCA0355%', 'LCA0359%', 'LCA0360%', 'LCA0361%'
]);

select * from barbour_inventory;

SELECT DISTINCT product_code
FROM barbour_inventory
WHERE size ~ '^(XS|S|M|L|XL|XXL|3XL|4XL)$';

SELECT DISTINCT product_code
FROM barbour_inventory
WHERE size ~ '^(30|32|34|36|38|40|42|44)$';

SELECT DISTINCT product_code
FROM barbour_inventory
WHERE size ~ '^(XS|S|M|L|XL|XXL|3XL|4XL)$'
  AND product_code NOT IN ('MWX0700OL51', 'MWX0700RU71', 'MWX0700NY51', 'MQU0240OL71', 'MQU0240BK11', 'MQU0240NY92', 'MWX0339OL71', 'MWX0339NY92', 'MWX0339BK72');


SELECT * from barbour_inventory where product_code = 'LWX1515BK71'


SELECT DISTINCT product_code
FROM barbour_inventory
WHERE size ~ '^(8|10|12|14|16|18)$'
  AND product_code NOT IN ('LQU1012PI14', 'LQU1012NY71', 'LQU1012OL51',
  'LQU1012BE34', 'LWX0668OL71', 'LWX0667SG91', 'LWX0667RU52', 'LWX0667NY91', 'LWX0667BR31', 'LWX0667BK11', 'LQU0475NY91', 'LQU0475BK91', 'LQU0475OL91',
  'LQU0475BE93', 'LQU0471NY91', 'LQU0471BK91', 'LQU0471OL91');

select * from barbour_inventory where channel_item_id = '969817808097'

select * from barbour_inventory where  product_code = 'LQS0058GN91'

select * from barbour_offers where product_code = 'LQS0058GN91'


select distinct product_code from clarks_jingya_inventory where gender ILIKE '%女%'









WITH params AS (
  SELECT 3::int AS min_available_sizes, 20::numeric AS min_discount_pct
),
base AS (
  SELECT
    o.product_code,
    o.site_name,
    MIN(o.original_price_gbp)            AS rrp_gbp,
    MIN(o.sale_price_gbp)                AS sale_gbp,      -- 生成列
    MAX(o.discount_pct)                  AS discount_pct,  -- 生成列
    STRING_AGG(DISTINCT o.size, ',' ORDER BY o.size)
      FILTER (WHERE o.can_order)         AS sizes_available,
    COUNT(DISTINCT o.size)
      FILTER (WHERE o.can_order)         AS available_count
  FROM barbour_offers o, params p
  WHERE o.is_active
    AND o.discount_pct >= p.min_discount_pct
  GROUP BY o.product_code, o.site_name
)
SELECT
  product_code,
  site_name,
  rrp_gbp::numeric(10,2)   AS original_price_gbp,
  sale_gbp::numeric(10,2)  AS discount_price_gbp,
  discount_pct,
  sizes_available
FROM base, params p
WHERE available_count >= p.min_available_sizes
ORDER BY discount_pct DESC, sale_gbp ASC, product_code ASC;


select * from barbour_offers where original_price_gbp IS NOT NULL




select * from barbour_offers where discount_pct > 15



WITH params AS (
  SELECT 15::numeric AS min_discount_pct
),
base AS (
  SELECT
    o.product_code,
    o.site_name,
    MIN(o.original_price_gbp) AS rrp_gbp,
    MIN(o.sale_price_gbp)     AS sale_gbp,
    MAX(o.discount_pct)       AS discount_pct,
    STRING_AGG(DISTINCT o.size, ',' ORDER BY o.size) AS all_sizes
  FROM barbour_offers o, params p
  WHERE o.is_active
    AND o.discount_pct > p.min_discount_pct
  GROUP BY o.product_code, o.site_name
)
SELECT
  product_code,
  site_name,
  rrp_gbp::numeric(10,2)  AS original_price_gbp,
  sale_gbp::numeric(10,2) AS discount_price_gbp,
  discount_pct,
  all_sizes
FROM base
ORDER BY discount_pct DESC, sale_gbp ASC, product_code ASC;



select * from barbour_supplier_map


select * from barbour_inventory where product_code ='MWX2341BK11'



SELECT 
  COUNT(*)                        AS offers_total,
  SUM(CASE WHEN product_code IS NOT NULL THEN 1 ELSE 0 END) AS offers_with_code,
  SUM(CASE WHEN product_code IS NULL THEN 1 ELSE 0 END)     AS offers_without_code
FROM barbour_offers
WHERE is_active = TRUE;

====10

SELECT COUNT(*) AS offer_rows_mapped
FROM barbour_offers bo
JOIN barbour_supplier_map sm
  ON lower(trim(sm.product_code)) = lower(trim(bo.product_code))
 AND lower(trim(sm.site_name))    = lower(trim(bo.site_name))
WHERE bo.is_active = TRUE 
  AND bo.product_code IS NOT NULL;

===0


SELECT bo.site_name,
       SUM(CASE WHEN bo.product_code IS NOT NULL THEN 1 ELSE 0 END) AS with_code,
       SUM(CASE WHEN bo.product_code IS NULL THEN 1 ELSE 0 END)     AS without_code
FROM barbour_offers bo
WHERE bo.is_active = TRUE
GROUP BY bo.site_name
ORDER BY without_code DESC;

===10


SELECT
  bo.product_code,
  bo.site_name,
  bo.size,
  bo.offer_url,
  bo.price_gbp,
  bo.sale_price_gbp,
  bo.stock_count,
  bo.last_checked
FROM barbour_offers bo
JOIN barbour_supplier_map sm
  ON lower(trim(sm.product_code)) = lower(trim(bo.product_code))
 AND lower(trim(sm.site_name))    = lower(trim(bo.site_name))
WHERE bo.is_active = TRUE
  AND bo.product_code IS NOT NULL


  ===NO DATA




SELECT DISTINCT product_code FROM barbour_inventory 
WHERE size ~ '^(XS|S|M|L|XL|XXL|3XL|4XL)$' 
AND product_code NOT IN  ('MWX0700OL51', 'MWX0700RU71', 'MWX0700NY51', 'MQU0240OL71', 
'MQU0240BK11', 'MQU0240NY92', 'MWX0339OL71', 'MWX0339NY92', 'MWX0339BK72');


"SELECT DISTINCT product_code FROM barbour_inventory WHERE size ~ '^(XS|S|M|L|XL|XXL|3XL|4XL)$' AND product_code NOT IN  ('MWX0700OL51', 'MWX0700RU71', 'MWX0700NY51', 'MQU0240OL71', 'MQU0240BK11', 'MQU0240NY92', 'MWX0339OL71', 'MWX0339NY92', 'MWX0339BK72');




SELECT * 
FROM barbour_inventory where product_code = 'LSP0242OL51'

select * from barbour_offers where product_code = 'LCA0353BK11'


select * from barbour_supplier_map where product_code = 'LCA0353BK11'


select * from barbour_products