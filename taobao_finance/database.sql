DROP TABLE IF EXISTS taobao_order_logistics;

CREATE TABLE taobao_order_logistics (
    id SERIAL PRIMARY KEY,

    order_id            VARCHAR(32) NOT NULL,      -- 订单编号（唯一）
    payment_id          VARCHAR(64),                -- 支付单号
    payment_detail      TEXT,                       -- 支付详情
    total_amount        NUMERIC(12,2),              -- 总金额
    order_status        VARCHAR(64),                -- 订单状态

    tracking_no         VARCHAR(64),                -- 物流单号
    logistics_company   VARCHAR(64),                -- 物流公司
    merchant_note       TEXT,                       -- 商家备注

    -- ===== 分销识别 & 利润 =====
    is_jingya_order     BOOLEAN DEFAULT FALSE,      -- 是否鲸芽分销订单
    sales_mode          VARCHAR(16),                -- 经营模式：分销 / 普通
    jingya_profit       NUMERIC(12,2),              -- 鲸芽分销利润

    -- ===== 财务字段 =====
    refund_amount       NUMERIC(12,2),              -- 退款金额
    compensation_amount NUMERIC(12,2),              -- 主动赔付金额
    payout_amount       NUMERIC(12,2),              -- 确认收货打款金额

    source_file         VARCHAR(255),               -- 来源文件名
    imported_at         TIMESTAMP DEFAULT NOW(),    -- 导入时间

    -- ===== 关键：唯一约束 =====
    CONSTRAINT uq_taobao_order_logistics_order_id UNIQUE (order_id)
);
