select * from export_shipments

truncate table export_shipments;


SELECT COUNT(*) AS missing_pdf_meta
FROM export_shipments
WHERE poe_mrn IS NULL OR poe_office IS NULL OR poe_date IS NULL;


SELECT COUNT(*) AS missing_invoice_fields
FROM export_shipments
WHERE COALESCE(NULLIF(shipment_id, ''), NULL) IS NULL
   OR COALESCE(NULLIF(lp_number, ''), NULL) IS NULL
   OR COALESCE(NULLIF(skuid, ''), NULL) IS NULL;


SELECT poe_file,
       SUM(CASE WHEN poe_mrn   IS NULL THEN 1 ELSE 0 END) AS miss_mrn,
       SUM(CASE WHEN poe_office IS NULL THEN 1 ELSE 0 END) AS miss_office,
       SUM(CASE WHEN poe_date  IS NULL THEN 1 ELSE 0 END) AS miss_date,
       COUNT(*) AS rows_
FROM export_shipments
GROUP BY poe_file
ORDER BY rows_ DESC;