


select * from barbour_products where style_name ILIKE '%beadnell%' and color ILIKE '%sage%';

select distinct color_code,style_name,color
from barbour_products where style_name ILIKE '%beadnell%' and color_code ILIKE '%LQU0471%';


select distinct color_code,style_name,color from barbour_products where color_code ILIKE '%LWX0667NY91%';

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

select COUNT(*) from offers where site_name = 'Barbour';

select COUNT(*) from barbour_products;

select * from offers where site_name = 'Barbour';

select * from barbour_products where color_code ILIKE '%LQU1776%';


select * from barbour_products;

select * from offers;


WITH sku_sizes AS (
  SELECT color_code, COUNT(*) AS total_sizes
  FROM barbour_products
  GROUP BY color_code
),
site_coverage AS (
  SELECT
    o.color_code,
    o.site_name,
    COUNT(DISTINCT o.size) AS available_sizes
  FROM offers o
  JOIN barbour_products p
    ON p.color_code = o.color_code AND p.size = o.size
  WHERE
    o.can_order = TRUE
    AND (
      o.stock_status IS NULL
      OR o.stock_status ILIKE 'in stock'
      OR o.stock_status = '有货'
    )
  GROUP BY o.color_code, o.site_name
),
full_sites AS (
  SELECT sc.color_code, sc.site_name
  FROM site_coverage sc
  JOIN sku_sizes s USING (color_code)
  WHERE sc.available_sizes = s.total_sizes
),
qualified AS (
  SELECT color_code, COUNT(DISTINCT site_name) AS site_count
  FROM full_sites
  GROUP BY color_code
  HAVING COUNT(DISTINCT site_name) >= 2
)
SELECT
  q.color_code,
  MIN(p.style_name) AS style_name,
  ARRAY_AGG(DISTINCT p.size ORDER BY p.size) AS all_sizes,
  ARRAY_AGG(DISTINCT f.site_name ORDER BY f.site_name) AS full_sites,
  MAX(q.site_count) AS site_count         -- ← 加出来
FROM qualified q
JOIN barbour_products p USING (color_code)
JOIN full_sites f USING (color_code)
GROUP BY q.color_code
ORDER BY site_count DESC, q.color_code;    -- ← 用上面的别名排序



SELECT DISTINCT color
FROM barbour_products
WHERE lower(color) LIKE '%empire%';




WITH sku_sizes AS (
  SELECT color_code, COUNT(*) AS total_sizes
  FROM barbour_products
  GROUP BY color_code
),
site_coverage AS (
  SELECT
    o.color_code,
    o.site_name,
    COUNT(DISTINCT o.size) AS available_sizes
  FROM offers o
  JOIN barbour_products p
    ON p.color_code = o.color_code AND p.size = o.size
  WHERE
    o.can_order = TRUE
    AND (
      o.stock_status IS NULL
      OR o.stock_status ILIKE 'in stock'
      OR o.stock_status = '有货'
    )
  GROUP BY o.color_code, o.site_name
),
full_sites AS (
  SELECT sc.color_code, sc.site_name
  FROM site_coverage sc
  JOIN sku_sizes s USING (color_code)
  WHERE sc.available_sizes = s.total_sizes
),
qualified AS (
  SELECT color_code, COUNT(DISTINCT site_name) AS site_count
  FROM full_sites
  GROUP BY color_code
  HAVING COUNT(DISTINCT site_name) >= 2
)
SELECT
  q.color_code,
  MIN(p.style_name) AS style_name,
  ARRAY_AGG(DISTINCT p.size ORDER BY p.size) AS all_sizes,
  ARRAY_AGG(DISTINCT f.site_name ORDER BY f.site_name) AS full_sites,
  MAX(q.site_count) AS site_count
FROM qualified q
JOIN barbour_products p USING (color_code)
JOIN full_sites f USING (color_code)
WHERE q.color_code LIKE 'MQU%'    -- ✅ 只要 MCA 开头的 color_code
GROUP BY q.color_code
ORDER BY site_count DESC, q.color_code;



select distinct product_code from barbour_inventory

select count(*) from offers;

select * from camper_inventory;

select count(*) from barbour_products;

select * from barbour_inventory where product_code ILIKE '%LWX0667%';

select * from barbour_inventory where product_code = 'LWX0667SG91';
;
select * from barbour_products where color_code = 'MCA1051NY71';

select * from barbour_products where style_name ILIKE '%Ashby %';

select * from barbour_products where style_name ILIKE '%beadnell%'

select * from offers where color_code = 'LWX0667SG91';


SELECT site_name, size, stock_status, can_order
FROM offers
WHERE color_code = 'MCA1051NY71'
ORDER BY site_name, size;

select * from barbour_products where style_name ILIKE '%bedale%';

select * from barbour_products where color_code ILIKE '%LSP0220%';

select * from offers where color_code ILIKE '%LSP0220%';

SELECT distinct color_code
FROM barbour_products
WHERE color_code LIKE ANY (ARRAY[
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
WHERE size ~ '^(8|10|12|14|16|19)$'
  AND product_code NOT IN ('MWX0700OL51', 'MWX0700RU71', 'MWX0700NY51', 'MQU0240OL71', 'MQU0240BK11', 'MQU0240NY92', 'MWX0339OL71', 'MWX0339NY92', 'MWX0339BK72');
