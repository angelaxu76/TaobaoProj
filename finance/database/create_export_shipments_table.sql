-- ==========================================
-- Recreate table: public.export_shipments
-- 用于生成 Export Evidence Summary 的底层明细表
-- ==========================================

BEGIN;

-- 1) 明细表：逐行记录（同一票可能多行）
DROP VIEW IF EXISTS public.export_shipments_summary;
DROP TABLE IF EXISTS public.export_shipments;

CREATE TABLE public.export_shipments (
  id                      BIGSERIAL PRIMARY KEY,

  -- 文件/目录定位（导入脚本已使用）
  folder_name             TEXT NOT NULL,              -- 例如 20251017
  invoice_file            TEXT,                       -- 发票源文件名（UK→HK）
  poe_file                TEXT,                       -- POE 源文件名

  -- 发票明细（从Excel读取的逐行）
  shipment_id             TEXT,                       -- 票 / 运单 / 组批号（外层归组键）
  skuid                   TEXT,                       -- 行项目 SKU/自编码
  lp_number               TEXT,                       -- 包裹号/面单号（如有多件拆分）
  product_description     TEXT,                       -- 商品描述
  value_gbp               NUMERIC(18,2),              -- 行金额（GBP）
  quantity                INTEGER,                    -- 行数量
  net_weight_kg           NUMERIC(18,3),              -- 行净重（KG）
  hs_code                 TEXT,                       -- 税号（可选）

  -- POE 解析信息（从 PDF 抓取）
  poe_id                  TEXT,                       -- 如 SD10...
  poe_mrn                 TEXT,                       -- MRN：25GBXXXXXXXXXXXXXXX
  poe_office              TEXT,                       -- Office of Exit：GB000XXXX
  poe_date                DATE,                       -- 离境日期

  -- ===== 票级补充信息（用于 PDF 汇总）=====
  uk_invoice_no           TEXT,                       -- UK→HK 发票号（建议填写）
  uk_invoice_date         DATE,                       -- UK→HK 发票日期
  uk_po_number            TEXT,                       -- 内部PO/对账号（可选）
  brand                   TEXT,                       -- 品牌（Camper/Clarks/...）
  currency                TEXT DEFAULT 'GBP',         -- 货币，默认 GBP

  -- 票级合计（可由脚本/SQL 回填）
  total_value_gbp         NUMERIC(18,2),              -- 票级合计金额（GBP）
  total_quantity          INTEGER,                    -- 票级合计数量
  total_gross_weight_kg   NUMERIC(18,3),              -- 票级毛重（若有）

  -- 物流识别（便于在 PDF 抬头展示）
  carrier_name            TEXT,                       -- 承运商（ECMS/Cainiao/…）
  tracking_no             TEXT,                       -- 主运单 / 跟踪号
  package_count           INTEGER,                    -- 总件数（如 POE/发票提供）

  -- 审计字段
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2) 更新时间戳触发器（可选但推荐）
DROP TRIGGER IF EXISTS trg_export_shipments_updated_at ON public.export_shipments;
DROP FUNCTION IF EXISTS public.fn_touch_updated_at();

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

-- 3) 实用索引（加速聚合与检索）
CREATE INDEX idx_export_shipments_folder ON public.export_shipments(folder_name);
CREATE INDEX idx_export_shipments_invoice_no ON public.export_shipments(uk_invoice_no);
CREATE INDEX idx_export_shipments_poe_mrn ON public.export_shipments(poe_mrn);
CREATE INDEX idx_export_shipments_shipment ON public.export_shipments(shipment_id);
CREATE INDEX idx_export_shipments_brand ON public.export_shipments(brand);

-- 4) （可选）去重约束：同一票据下的行唯一性
-- 视你的数据来源而定，若会重复导入可打开此唯一约束：
-- ALTER TABLE public.export_shipments
--   ADD CONSTRAINT uq_export_row UNIQUE (folder_name, uk_invoice_no, skuid, COALESCE(lp_number,''));

-- 5) 票级汇总视图：用于直接喂给 PDF 生成器
CREATE VIEW public.export_shipments_summary AS
SELECT
  -- 汇总分组键（按 folder + 发票号 最稳）
  folder_name,
  COALESCE(uk_invoice_no, shipment_id) AS invoice_key,
  MIN(uk_invoice_no)         AS uk_invoice_no,
  MIN(uk_invoice_date)       AS uk_invoice_date,
  MIN(uk_po_number)          AS uk_po_number,
  MIN(brand)                 AS brand,
  MIN(currency)              AS currency,

  -- POE / 物流（按票级取一个非空）
  MIN(poe_id)                AS poe_id,
  MIN(poe_mrn)               AS poe_mrn,
  MIN(poe_office)            AS poe_office,
  MIN(poe_date)              AS poe_date,
  MIN(carrier_name)          AS carrier_name,
  MIN(tracking_no)           AS tracking_no,
  MAX(package_count)         AS package_count,

  -- 合计值（若表内 total_* 已预填，可优先用 total_*，否则聚合行）
  COALESCE(MAX(total_value_gbp),
           ROUND(SUM(value_gbp)::NUMERIC, 2))        AS total_value_gbp,
  COALESCE(MAX(total_quantity),
           SUM(quantity))                             AS total_quantity,
  COALESCE(MAX(total_gross_weight_kg),
           ROUND(SUM(net_weight_kg)::NUMERIC, 3))    AS total_gross_weight_kg,

  -- 供明细页使用的统计（可选）
  COUNT(*) AS line_count,
  MIN(created_at) AS created_at_min,
  MAX(updated_at) AS updated_at_max
FROM public.export_shipments
GROUP BY folder_name, COALESCE(uk_invoice_no, shipment_id);

COMMIT;
