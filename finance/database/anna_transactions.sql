BEGIN;

CREATE TABLE IF NOT EXISTS public.anna_transactions (
  id BIGSERIAL PRIMARY KEY,

  -- 唯一键：用于去重导入（优先用 ANNA 自带 transaction id；没有就用你生成的hash）
  anna_txn_uid TEXT NOT NULL UNIQUE,

  authorised_on TIMESTAMPTZ,     -- 下单/扣款时间（ANNA: Authorised on）
  settled_on DATE,               -- 入账时间（如有）
  amount NUMERIC(18,2) NOT NULL,
  currency TEXT DEFAULT 'GBP',

  counterparty TEXT,             -- 商户/对方
  description TEXT,
  txn_type TEXT,
  anna_category TEXT,

  -- 你关心的“匹配字段”
  supplier_name_norm TEXT,       -- 规范供货商名（CLARKS/ECCO…）
  order_number TEXT,             -- 官网订单号（= export_shipments.supplier_order_no）
  brand TEXT,                    -- 可选
  is_refund BOOLEAN DEFAULT FALSE,

  note_tag TEXT,
  match_status TEXT DEFAULT 'UNMATCHED', -- MATCHED/UNMATCHED/NEEDS_REVIEW

  raw_row_json JSONB,            -- 可选：原始行存档，审计追溯

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 常用索引：按订单/供货商/时间查
CREATE INDEX IF NOT EXISTS idx_anna_tx_order_number
  ON public.anna_transactions (order_number);

CREATE INDEX IF NOT EXISTS idx_anna_tx_supplier
  ON public.anna_transactions (supplier_name_norm);

CREATE INDEX IF NOT EXISTS idx_anna_tx_authorised
  ON public.anna_transactions (authorised_on);

COMMIT;
