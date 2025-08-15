


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
