BEGIN;

DROP VIEW IF EXISTS public.export_shipments_summary;
DROP TABLE IF EXISTS public.export_shipments CASCADE;

CREATE TABLE public.export_shipments (
  id                      BIGSERIAL PRIMARY KEY,

  folder_name             TEXT NOT NULL,
  invoice_file            TEXT,
  poe_file                TEXT,

  shipment_id             TEXT,
  skuid                   TEXT,
  lp_number               TEXT,
  product_description     TEXT,
  value_gbp               NUMERIC(18,2),
  quantity                INTEGER,
  net_weight_kg           NUMERIC(18,3),
  hs_code                 TEXT,

  poe_id                  TEXT,
  poe_mrn                 TEXT,
  poe_office              TEXT,
  poe_date                DATE,

  -- 新增的三个字段
  supplier_name            TEXT,
  supplier_order_no        TEXT,
  purchase_unit_cost_gbp   NUMERIC(18,4),

  uk_invoice_no           TEXT,
  uk_invoice_date         DATE,
  uk_po_number            TEXT,
  brand                   TEXT,
  currency                TEXT DEFAULT 'GBP',

  total_value_gbp         NUMERIC(18,2),
  total_quantity          INTEGER,
  total_gross_weight_kg   NUMERIC(18,3),

  carrier_name            TEXT,
  tracking_no             TEXT,
  package_count           INTEGER,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_export_shipments_updated_at ON public.export_shipments;
DROP FUNCTION IF EXISTS public.fn_touch_updated_at;

CREATE FUNCTION public.fn_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_export_shipments_updated_at
BEFORE UPDATE ON public.export_shipments
FOR EACH ROW EXECUTE FUNCTION public.fn_touch_updated_at();

CREATE INDEX idx_export_shipments_folder     ON public.export_shipments(folder_name);
CREATE INDEX idx_export_shipments_invoice_no ON public.export_shipments(uk_invoice_no);
CREATE INDEX idx_export_shipments_poe_mrn    ON public.export_shipments(poe_mrn);
CREATE INDEX idx_export_shipments_shipment   ON public.export_shipments(shipment_id);
CREATE INDEX idx_export_shipments_brand      ON public.export_shipments(brand);

CREATE VIEW public.export_shipments_summary AS
SELECT
  folder_name,
  COALESCE(uk_invoice_no, shipment_id) AS invoice_key,
  MIN(uk_invoice_no) AS uk_invoice_no,
  MIN(uk_invoice_date) AS uk_invoice_date,
  MIN(uk_po_number) AS uk_po_number,
  MIN(brand) AS brand,
  MIN(currency) AS currency,
  MIN(poe_id) AS poe_id,
  MIN(poe_mrn) AS poe_mrn,
  MIN(poe_office) AS poe_office,
  MIN(poe_date) AS poe_date,
  MIN(carrier_name) AS carrier_name,
  MIN(tracking_no) AS tracking_no,
  MAX(package_count) AS package_count,
  COALESCE(MAX(total_value_gbp),
           ROUND(SUM(value_gbp)::NUMERIC,2)) AS total_value_gbp,
  COALESCE(MAX(total_quantity),
           SUM(quantity)) AS total_quantity,
  COALESCE(MAX(total_gross_weight_kg),
           ROUND(SUM(net_weight_kg)::NUMERIC,3)) AS total_gross_weight_kg,
  COUNT(*) AS line_count,
  MIN(created_at) AS created_at_min,
  MAX(updated_at) AS updated_at_max
FROM public.export_shipments
GROUP BY folder_name, COALESCE(uk_invoice_no, shipment_id);

COMMIT;
