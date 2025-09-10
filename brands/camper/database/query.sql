

select * from camper_inventory where product_code = '44695-088'


select DISTINCT product_code from camper_inventory where channel_item_id IS NOT null and gender = '女款' and  product_code = '44695-088'


select DISTINCT product_code from camper_inventory where channel_item_id IS NOT null and gender = '女款'


select * from camper

select * from camper_inventory where product_code ='K400798-005'

select * from camper_inventory where 


SELECT
    product_code AS "商品编码",
    MAX(channel_product_id) FILTER (WHERE channel_product_id IS NOT NULL AND channel_product_id <> '') AS "渠道产品ID",
    MAX(product_title) FILTER (WHERE product_title IS NOT NULL AND product_title <> '') AS product_title,
    SUM(COALESCE(stock_count, 0)) AS "总库存"
FROM camper_inventory
GROUP BY product_code
HAVING SUM(COALESCE(stock_count, 0)) < 5
ORDER BY "总库存" ASC, "商品编码" ASC;


SELECT
  COUNT(*)                                           AS total_rows,
  COUNT(*) FILTER (WHERE NULLIF(channel_product_id,'') IS NOT NULL) AS filled_rows,
  COUNT(DISTINCT product_code)                       AS codes_total,
  COUNT(DISTINCT product_code) FILTER (
      WHERE EXISTS (
          SELECT 1 FROM camper_inventory ci2
          WHERE ci2.product_code = camper_inventory.product_code
            AND NULLIF(ci2.channel_product_id,'') IS NOT NULL
      )
  )                                                  AS codes_with_any_channel
FROM camper_inventory;

SELECT product_code, size, '[' || channel_product_id || ']' AS raw_id
FROM camper_inventory
WHERE product_code = 'K100226-141'
ORDER BY size;

select size, stock_count from camper_inventory where product_code = 'K201803-001'

"select size, stock_count from camper_inventory where product_code = '"+ productCode+ "'"


select DISTINCT product_code from camper_inventory where channel_item_id IS NOT null and gender = '女款' and product_code = 'K400758-006' ORDER BY product_code;