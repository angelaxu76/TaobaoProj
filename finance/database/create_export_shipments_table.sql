-- DDL for export_shipments table
-- 建表（全新环境）
CREATE TABLE IF NOT EXISTS public.export_shipments (
    id              BIGSERIAL PRIMARY KEY,
    folder_name     TEXT,
    invoice_file    TEXT,
    poe_file        TEXT,
    poe_id          TEXT,
    poe_mrn         TEXT,
    poe_office      TEXT,
    poe_date        DATE,
    shipment_id     TEXT,
    skuid           TEXT,
    lp_number       TEXT,
    product_description TEXT,
    value_gbp       NUMERIC,
    quantity        INTEGER,
    net_weight_kg   NUMERIC,
    hs_code         TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);


-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_export_shipments_poe_id ON export_shipments(poe_id);
CREATE INDEX IF NOT EXISTS idx_export_shipments_mrn ON export_shipments(hmrc_mrn);
CREATE INDEX IF NOT EXISTS idx_export_shipments_skuid ON export_shipments(skuid);