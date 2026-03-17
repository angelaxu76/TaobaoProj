-- 为 export_shipments 表添加退货追踪字段
-- 执行一次即可，幂等（使用 IF NOT EXISTS 语法）
-- 执行：psql -h 192.168.1.44 -U postgres -d taobao_inventory_db -f add_return_fields.sql

ALTER TABLE public.export_shipments
  ADD COLUMN IF NOT EXISTS is_returned    BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS return_date    DATE,
  ADD COLUMN IF NOT EXISTS credit_note_no TEXT;

CREATE INDEX IF NOT EXISTS idx_export_shipments_is_returned
  ON public.export_shipments(is_returned)
  WHERE is_returned = TRUE;

CREATE INDEX IF NOT EXISTS idx_export_shipments_credit_note_no
  ON public.export_shipments(credit_note_no);
