

select * from camper_inventory where product_code = '44695-088'


select DISTINCT product_code from camper_inventory where channel_item_id IS NOT null and gender = '女款' and  product_code = '44695-088'


select DISTINCT product_code from camper_inventory where channel_item_id IS NOT null and gender = '女款'


select * from camper

select * from camper_inventory where product_code ='K101023-002'

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



SELECT product_code, channel_product_id, original_price_gbp, discount_price_gbp
FROM camper_inventory
WHERE product_code IN ('80003-104','K200631-009','K201659-009') LIMIT 50;


select * from camper_inventory where channel_product_id = '968827262430'

SELECT COUNT(*) AS with_channel_id_cnt
FROM camper_inventory
WHERE NULLIF(TRIM(channel_product_id), '') IS NOT NULL;

SELECT COUNT(DISTINCT NULLIF(TRIM(channel_product_id), '')) AS distinct_channel_id_cnt
FROM camper_inventory;


update camper_inventory set stock_count = 10 where stock_count >= 10000


select * from camper_inventory where product_code = 'K100927-018'