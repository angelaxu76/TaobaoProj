-- DDL for export_shipments table
CREATE TABLE IF NOT EXISTS export_shipments (
    id SERIAL PRIMARY KEY,
    skuid TEXT,
    lp_number TEXT,
    product_description TEXT,
    value_gbp NUMERIC(12,2),
    quantity NUMERIC(12,2),
    net_weight_kg NUMERIC(14,3),
    hs_code TEXT,
    poe_id TEXT,
    hmrc_mrn TEXT,
    poe_filename TEXT,
    export_date DATE,
    office_of_exit TEXT,
    src_folder TEXT,
    src_invoice_file TEXT,
    src_poe_file TEXT
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_export_shipments_poe_id ON export_shipments(poe_id);
CREATE INDEX IF NOT EXISTS idx_export_shipments_mrn ON export_shipments(hmrc_mrn);
CREATE INDEX IF NOT EXISTS idx_export_shipments_skuid ON export_shipments(skuid);