-- Table: bridge_bom_component
-- 桥接表，用于表达多对多或层级组件关系。
CREATE TABLE bridge_bom_component (
    -- bom_comp_id: BOM 组件桥接表主键。
    bom_comp_id INTEGER PRIMARY KEY,
    -- bom_id: 所属 BOM 编号。
    bom_id TEXT NOT NULL,
    -- component_material_id: 组件物料编号，对应物料主表。
    component_material_id TEXT NOT NULL,
    -- component_qty: 单个成品消耗的组件数量。
    component_qty REAL NOT NULL,
    -- scrap_rate: 组件损耗率。
    scrap_rate REAL NOT NULL,
    -- component_group_cd: 组件分组代码。
    component_group_cd TEXT NOT NULL
);

-- Table: code_defect_type
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_defect_type (
    -- defect_type_cd: 业务代码字段，通常需要关联代码表翻译。
    defect_type_cd TEXT PRIMARY KEY,
    -- defect_type_nm: 中文或业务可读名称。
    defect_type_nm TEXT NOT NULL,
    -- severity_cd: 业务代码字段，通常需要关联代码表翻译。
    severity_cd TEXT NOT NULL,
    -- defect_group_cd: 业务代码字段，通常需要关联代码表翻译。
    defect_group_cd TEXT DEFAULT 'QUALITY',
    -- display_seq: 顺序号字段。
    display_seq INTEGER DEFAULT 10
);

-- Table: code_inv_txn_type
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_inv_txn_type (
    -- inv_txn_type_cd: 业务代码字段，通常需要关联代码表翻译。
    inv_txn_type_cd TEXT PRIMARY KEY,
    -- inv_txn_type_nm: 中文或业务可读名称。
    inv_txn_type_nm TEXT NOT NULL,
    -- direction_cd: 业务代码字段，通常需要关联代码表翻译。
    direction_cd TEXT NOT NULL,
    -- impact_stock_fg: 布尔标记字段，1/0 表示是或否。
    impact_stock_fg INTEGER DEFAULT 1,
    -- display_seq: 顺序号字段。
    display_seq INTEGER DEFAULT 10
);

-- Table: code_order_type
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_order_type (
    -- order_type_cd: 业务代码字段，通常需要关联代码表翻译。
    order_type_cd TEXT PRIMARY KEY,
    -- order_type_nm: 中文或业务可读名称。
    order_type_nm TEXT NOT NULL,
    -- priority_rank: 代码表补充属性字段。
    priority_rank INTEGER DEFAULT 1,
    -- channel_cd: 业务代码字段，通常需要关联代码表翻译。
    channel_cd TEXT DEFAULT 'DIRECT'
);

-- Table: code_sales_order_status
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_sales_order_status (
    -- sales_order_status_cd: 业务代码字段，通常需要关联代码表翻译。
    sales_order_status_cd TEXT PRIMARY KEY,
    -- sales_order_status_nm: 中文或业务可读名称。
    sales_order_status_nm TEXT NOT NULL,
    -- is_valid_order: 代码表补充属性字段。
    is_valid_order INTEGER NOT NULL,
    -- lifecycle_stage_cd: 业务代码字段，通常需要关联代码表翻译。
    lifecycle_stage_cd TEXT DEFAULT 'OPEN',
    -- display_seq: 顺序号字段。
    display_seq INTEGER DEFAULT 10
);

-- Table: code_supplier_class
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_supplier_class (
    -- supplier_class_cd: 业务代码字段，通常需要关联代码表翻译。
    supplier_class_cd TEXT PRIMARY KEY,
    -- supplier_class_nm: 中文或业务可读名称。
    supplier_class_nm TEXT NOT NULL,
    -- class_weight: 代码表补充属性字段。
    class_weight REAL DEFAULT 1.0,
    -- risk_band_cd: 风险相关业务字段。
    risk_band_cd TEXT DEFAULT 'MED'
);

-- Table: code_uom
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_uom (
    -- uom_cd: 业务代码字段，通常需要关联代码表翻译。
    uom_cd TEXT PRIMARY KEY,
    -- uom_nm: 中文或业务可读名称。
    uom_nm TEXT NOT NULL,
    -- uom_group_cd: 业务代码字段，通常需要关联代码表翻译。
    uom_group_cd TEXT DEFAULT 'QTY',
    -- decimal_precision: 代码表补充属性字段。
    decimal_precision INTEGER DEFAULT 0
);

-- Table: code_work_order_status
-- 代码表，用于把状态码、类型码翻译成可读业务语义。
CREATE TABLE code_work_order_status (
    -- work_order_status_cd: 业务代码字段，通常需要关联代码表翻译。
    work_order_status_cd TEXT PRIMARY KEY,
    -- work_order_status_nm: 中文或业务可读名称。
    work_order_status_nm TEXT NOT NULL,
    -- is_active_order: 代码表补充属性字段。
    is_active_order INTEGER NOT NULL,
    -- display_seq: 顺序号字段。
    display_seq INTEGER DEFAULT 10,
    -- is_reportable: 代码表补充属性字段。
    is_reportable INTEGER DEFAULT 1
);

-- Table: dim_bin_loc
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_bin_loc (
    -- bin_id: 业务主键或关联键。
    bin_id TEXT PRIMARY KEY,
    -- wh_id: 业务主键或关联键。
    wh_id TEXT NOT NULL,
    -- zone_cd: 业务代码字段，通常需要关联代码表翻译。
    zone_cd TEXT NOT NULL,
    -- bin_status_cd: 业务代码字段，通常需要关联代码表翻译。
    bin_status_cd TEXT NOT NULL,
    -- temp_zone_cd: 业务代码字段，通常需要关联代码表翻译。
    temp_zone_cd TEXT DEFAULT 'AMB',
    -- max_pallet_qty: 数量字段。
    max_pallet_qty INTEGER DEFAULT 20,
    -- pick_path_seq: 顺序号字段。
    pick_path_seq INTEGER DEFAULT 1
);

-- Table: dim_bom_hdr
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_bom_hdr (
    -- bom_id: 业务主键或关联键。
    bom_id TEXT PRIMARY KEY,
    -- parent_material_id: 业务主键或关联键。
    parent_material_id TEXT NOT NULL,
    -- bom_version: 维度属性字段，用于描述主数据特征。
    bom_version TEXT NOT NULL,
    -- is_current_ver: 维度属性字段，用于描述主数据特征。
    is_current_ver INTEGER NOT NULL,
    -- eng_owner_nm: 中文或业务可读名称。
    eng_owner_nm TEXT DEFAULT 'ENG',
    -- release_dt_key: 日期键，文本格式 YYYYMMDD。
    release_dt_key TEXT DEFAULT '20250101',
    -- bom_status_cd: 业务代码字段，通常需要关联代码表翻译。
    bom_status_cd TEXT DEFAULT 'REL'
);

-- Table: dim_calendar_mth
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_calendar_mth (
    -- month_key: 月份键，文本格式 YYYYMM。
    month_key TEXT PRIMARY KEY,
    -- year_num: 维度属性字段，用于描述主数据特征。
    year_num INTEGER NOT NULL,
    -- month_num: 维度属性字段，用于描述主数据特征。
    month_num INTEGER NOT NULL,
    -- month_nm: 中文或业务可读名称。
    month_nm TEXT NOT NULL,
    -- fiscal_qtr: 维度属性字段，用于描述主数据特征。
    fiscal_qtr TEXT NOT NULL,
    -- workday_cnt: 工作日相关业务字段。
    workday_cnt INTEGER DEFAULT 21,
    -- holiday_cnt: 节假日相关业务字段。
    holiday_cnt INTEGER DEFAULT 9,
    -- season_cd: 季节相关业务字段。
    season_cd TEXT DEFAULT 'NORMAL'
);

-- Table: dim_customer
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_customer (
    -- customer_id: 客户主数据编号。
    customer_id TEXT PRIMARY KEY,
    -- customer_nm: 客户名称。
    customer_nm TEXT NOT NULL,
    -- cust_segment_cd: 客户细分代码。
    cust_segment_cd TEXT NOT NULL,
    -- region_cd: 客户区域代码。
    region_cd TEXT NOT NULL,
    -- credit_grade_cd: 客户信用等级。
    credit_grade_cd TEXT NOT NULL,
    -- sales_rep_nm: 负责客户的销售代表。
    sales_rep_nm TEXT DEFAULT 'TEAM_A',
    -- invoice_term_day: 开票账期天数。
    invoice_term_day INTEGER DEFAULT 30,
    -- channel_cd: 客户渠道代码。
    channel_cd TEXT DEFAULT 'DIRECT',
    -- customer_tier_cd: 客户层级代码。
    customer_tier_cd TEXT DEFAULT 'T2'
);

-- Table: dim_customer_addr
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_customer_addr (
    -- addr_id: 业务主键或关联键。
    addr_id INTEGER PRIMARY KEY,
    -- customer_id: 业务主键或关联键。
    customer_id TEXT NOT NULL,
    -- city_nm: 中文或业务可读名称。
    city_nm TEXT NOT NULL,
    -- province_nm: 中文或业务可读名称。
    province_nm TEXT NOT NULL,
    -- is_primary_addr: 维度属性字段，用于描述主数据特征。
    is_primary_addr INTEGER NOT NULL,
    -- postcode: 维度属性字段，用于描述主数据特征。
    postcode TEXT DEFAULT '200000',
    -- country_nm: 中文或业务可读名称。
    country_nm TEXT DEFAULT 'CN',
    -- addr_type_cd: 业务代码字段，通常需要关联代码表翻译。
    addr_type_cd TEXT DEFAULT 'SHIP'
);

-- Table: dim_customer_profile
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_customer_profile (
    -- customer_id: 客户主数据一对一档案表主键，对应客户主表。
    customer_id TEXT PRIMARY KEY,
    -- legal_entity_nm: 客户法定主体名称。
    legal_entity_nm TEXT NOT NULL,
    -- tax_reg_no: 客户税号。
    tax_reg_no TEXT NOT NULL,
    -- industry_cd: 客户所属行业代码。
    industry_cd TEXT NOT NULL,
    -- service_level_cd: 客户服务等级。
    service_level_cd TEXT NOT NULL,
    -- contract_signed_dt_key: 合同签订日期，文本格式 YYYYMMDD。
    contract_signed_dt_key TEXT NOT NULL,
    -- account_mgr_nm: 客户经理姓名。
    account_mgr_nm TEXT NOT NULL,
    -- digital_maturity_cd: 客户数字化成熟度分层。
    digital_maturity_cd TEXT NOT NULL
);

-- Table: dim_material
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_material (
    -- material_id: 物料主键。
    material_id TEXT PRIMARY KEY,
    -- material_sku: 物料编码。
    material_sku TEXT NOT NULL,
    -- material_nm: 物料名称。
    material_nm TEXT NOT NULL,
    -- material_type_cd: 物料类型代码，如 FG、RM。
    material_type_cd TEXT NOT NULL,
    -- base_uom_cd: 基础计量单位代码。
    base_uom_cd TEXT NOT NULL,
    -- prod_family_cd: 产品系列代码。
    prod_family_cd TEXT NOT NULL,
    -- std_cost_amt: 标准成本金额。
    std_cost_amt REAL NOT NULL,
    -- is_active_fg: 是否为活跃成品标记。
    is_active_fg INTEGER NOT NULL,
    -- planner_cd: 计划员编码。
    planner_cd TEXT NOT NULL,
    -- safety_stock_qty: 安全库存数量。
    safety_stock_qty INTEGER NOT NULL,
    -- lead_time_day: 提前期天数。
    lead_time_day INTEGER NOT NULL,
    -- default_supplier_id: 默认供应商编号。
    default_supplier_id TEXT,
    -- pack_spec: 包装规格。
    pack_spec TEXT,
    -- voltage_level: 电压等级冗余字段。
    voltage_level TEXT,
    -- color_cd: 颜色代码冗余字段。
    color_cd TEXT
);

-- Table: dim_material_alias
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_material_alias (
    -- alias_id: 业务主键或关联键。
    alias_id INTEGER PRIMARY KEY,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- alias_type_cd: 别名类型代码。
    alias_type_cd TEXT NOT NULL,
    -- alias_value: 物料别名或历史命名。
    alias_value TEXT NOT NULL,
    -- lang_cd: 业务代码字段，通常需要关联代码表翻译。
    lang_cd TEXT DEFAULT 'zh-CN',
    -- is_preferred_alias: 维度属性字段，用于描述主数据特征。
    is_preferred_alias INTEGER DEFAULT 0
);

-- Table: dim_plant
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_plant (
    -- plant_id: 工厂编号。
    plant_id TEXT PRIMARY KEY,
    -- plant_nm: 工厂名称。
    plant_nm TEXT NOT NULL,
    -- region_cd: 业务代码字段，通常需要关联代码表翻译。
    region_cd TEXT NOT NULL,
    -- plant_type_cd: 业务代码字段，通常需要关联代码表翻译。
    plant_type_cd TEXT NOT NULL,
    -- city_nm: 中文或业务可读名称。
    city_nm TEXT DEFAULT '上海',
    -- tz_cd: 业务代码字段，通常需要关联代码表翻译。
    tz_cd TEXT DEFAULT 'Asia/Shanghai',
    -- go_live_dt_key: 日期键，文本格式 YYYYMMDD。
    go_live_dt_key TEXT DEFAULT '20240101'
);

-- Table: dim_prod_line
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_prod_line (
    -- prod_line_id: 生产线编号。
    prod_line_id TEXT PRIMARY KEY,
    -- workshop_id: 业务主键或关联键。
    workshop_id TEXT NOT NULL,
    -- prod_line_nm: 生产线名称。
    prod_line_nm TEXT NOT NULL,
    -- line_status_cd: 生产线状态代码。
    line_status_cd TEXT NOT NULL,
    -- line_capacity_per_day: 产能相关业务字段。
    line_capacity_per_day INTEGER NOT NULL,
    -- line_category_cd: 业务代码字段，通常需要关联代码表翻译。
    line_category_cd TEXT DEFAULT 'ASM',
    -- oee_target: 维度属性字段，用于描述主数据特征。
    oee_target REAL DEFAULT 0.85,
    -- commission_dt_key: 日期键，文本格式 YYYYMMDD。
    commission_dt_key TEXT DEFAULT '20240101'
);

-- Table: dim_shift
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_shift (
    -- shift_cd: 业务代码字段，通常需要关联代码表翻译。
    shift_cd TEXT PRIMARY KEY,
    -- shift_nm: 中文或业务可读名称。
    shift_nm TEXT NOT NULL,
    -- shift_seq: 顺序号字段。
    shift_seq INTEGER NOT NULL,
    -- start_hhmm: 维度属性字段，用于描述主数据特征。
    start_hhmm TEXT DEFAULT '08:00',
    -- end_hhmm: 维度属性字段，用于描述主数据特征。
    end_hhmm TEXT DEFAULT '16:00',
    -- shift_type_cd: 业务代码字段，通常需要关联代码表翻译。
    shift_type_cd TEXT DEFAULT 'REG'
);

-- Table: dim_supplier
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_supplier (
    -- supplier_id: 供应商编号。
    supplier_id TEXT PRIMARY KEY,
    -- supplier_nm: 供应商名称。
    supplier_nm TEXT NOT NULL,
    -- supplier_class_cd: 供应商分类代码。
    supplier_class_cd TEXT NOT NULL,
    -- region_cd: 供应商区域代码。
    region_cd TEXT NOT NULL,
    -- on_time_target: 准时交付目标值。
    on_time_target REAL NOT NULL,
    -- buyer_nm: 采购员相关业务字段。
    buyer_nm TEXT DEFAULT 'BUYER_A',
    -- payment_term_day: 维度属性字段，用于描述主数据特征。
    payment_term_day INTEGER DEFAULT 60,
    -- supplier_status_cd: 业务代码字段，通常需要关联代码表翻译。
    supplier_status_cd TEXT DEFAULT 'ACTIVE',
    -- tax_region_cd: 业务代码字段，通常需要关联代码表翻译。
    tax_region_cd TEXT DEFAULT 'CN'
);

-- Table: dim_supplier_profile
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_supplier_profile (
    -- supplier_id: 供应商主数据一对一档案表主键，对应供应商主表。
    supplier_id TEXT PRIMARY KEY,
    -- legal_entity_nm: 供应商法定主体名称。
    legal_entity_nm TEXT NOT NULL,
    -- tax_reg_no: 供应商税号。
    tax_reg_no TEXT NOT NULL,
    -- quality_cert_cd: 供应商质量认证代码。
    quality_cert_cd TEXT NOT NULL,
    -- compliance_level_cd: 供应商合规等级代码。
    compliance_level_cd TEXT NOT NULL,
    -- contract_signed_dt_key: 合同签订日期，文本格式 YYYYMMDD。
    contract_signed_dt_key TEXT NOT NULL,
    -- category_mgr_nm: 供应商品类经理姓名。
    category_mgr_nm TEXT NOT NULL,
    -- esg_rating_cd: 供应商 ESG 评级代码。
    esg_rating_cd TEXT NOT NULL
);

-- Table: dim_wh
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_wh (
    -- wh_id: 业务主键或关联键。
    wh_id TEXT PRIMARY KEY,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- wh_nm: 中文或业务可读名称。
    wh_nm TEXT NOT NULL,
    -- wh_type_cd: 业务代码字段，通常需要关联代码表翻译。
    wh_type_cd TEXT NOT NULL,
    -- wh_mgr_nm: 中文或业务可读名称。
    wh_mgr_nm TEXT DEFAULT 'WH_TEAM',
    -- temp_ctrl_fg: 布尔标记字段，1/0 表示是或否。
    temp_ctrl_fg INTEGER DEFAULT 0,
    -- throughput_class_cd: 业务代码字段，通常需要关联代码表翻译。
    throughput_class_cd TEXT DEFAULT 'M'
);

-- Table: dim_workshop
-- 维度表，提供实体主数据与语义解释。
CREATE TABLE dim_workshop (
    -- workshop_id: 业务主键或关联键。
    workshop_id TEXT PRIMARY KEY,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- workshop_nm: 中文或业务可读名称。
    workshop_nm TEXT NOT NULL,
    -- workshop_type_cd: 业务代码字段，通常需要关联代码表翻译。
    workshop_type_cd TEXT NOT NULL,
    -- floor_no: 维度属性字段，用于描述主数据特征。
    floor_no INTEGER DEFAULT 1,
    -- workshop_mgr_nm: 中文或业务可读名称。
    workshop_mgr_nm TEXT DEFAULT 'WS_TEAM',
    -- cost_center_cd: 业务代码字段，通常需要关联代码表翻译。
    cost_center_cd TEXT DEFAULT 'CC1001'
);

-- Table: eav_material_attr
-- EAV 属性表，属性名称和值拆表存储。
CREATE TABLE eav_material_attr (
    -- attr_id: 业务主键或关联键。
    attr_id INTEGER PRIMARY KEY,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- attr_nm: EAV 属性名称，如 color、voltage。
    attr_nm TEXT NOT NULL,
    -- attr_value: EAV 属性值。
    attr_value TEXT NOT NULL,
    -- attr_uom_cd: 业务代码字段，通常需要关联代码表翻译。
    attr_uom_cd TEXT,
    -- attr_group_cd: 业务代码字段，通常需要关联代码表翻译。
    attr_group_cd TEXT DEFAULT 'GEN',
    -- is_searchable: 业务字段。
    is_searchable INTEGER DEFAULT 1
);

-- Table: fact_energy_usage_dly
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_energy_usage_dly (
    -- energy_id: 业务主键或关联键。
    energy_id INTEGER PRIMARY KEY,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- prod_line_id: 业务主键或关联键。
    prod_line_id TEXT NOT NULL,
    -- usage_dt_key: 日期键，文本格式 YYYYMMDD。
    usage_dt_key TEXT NOT NULL,
    -- kwh_qty: 耗电量相关业务字段。
    kwh_qty REAL NOT NULL,
    -- peak_kwh_qty: 耗电量、峰值相关业务字段。
    peak_kwh_qty REAL DEFAULT 0,
    -- offpeak_kwh_qty: 耗电量、峰值、谷值相关业务字段。
    offpeak_kwh_qty REAL DEFAULT 0,
    -- unit_cost_amt: 金额字段。
    unit_cost_amt REAL DEFAULT 0.72
);

-- Table: fact_forecast_mth
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_forecast_mth (
    -- forecast_id: 业务主键或关联键。
    forecast_id INTEGER PRIMARY KEY,
    -- month_key: 月份键，文本格式 YYYYMM。
    month_key TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- forecast_qty: 数量字段。
    forecast_qty INTEGER NOT NULL,
    -- forecast_version_cd: 业务代码字段，通常需要关联代码表翻译。
    forecast_version_cd TEXT DEFAULT 'V1',
    -- demand_source_cd: 业务代码字段，通常需要关联代码表翻译。
    demand_source_cd TEXT DEFAULT 'SOP',
    -- planner_adj_qty: 计划员相关业务字段。
    planner_adj_qty INTEGER DEFAULT 0
);

-- Table: fact_inv_balance_snap
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_inv_balance_snap (
    -- snap_id: 业务主键或关联键。
    snap_id INTEGER PRIMARY KEY,
    -- wh_id: 库存快照所属仓库编号。
    wh_id TEXT NOT NULL,
    -- material_id: 库存快照所属物料编号。
    material_id TEXT NOT NULL,
    -- snap_dt_key: 库存快照日期，文本格式 YYYYMMDD。
    snap_dt_key TEXT NOT NULL,
    -- on_hand_qty: 在手库存数量。
    on_hand_qty INTEGER NOT NULL,
    -- alloc_qty: 已分配库存数量，可用库存通常为在手减已分配。
    alloc_qty INTEGER NOT NULL,
    -- in_transit_qty: 在途库存数量。
    in_transit_qty INTEGER NOT NULL,
    -- cycle_count_diff_qty: 盘点差异数量。
    cycle_count_diff_qty INTEGER NOT NULL,
    -- frozen_qty: 冻结库存数量。
    frozen_qty INTEGER DEFAULT 0,
    -- qa_hold_qty: 质检冻结库存数量。
    qa_hold_qty INTEGER DEFAULT 0,
    -- expiry_risk_qty: 临期风险库存数量。
    expiry_risk_qty INTEGER DEFAULT 0
);

-- Table: fact_inv_txn
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_inv_txn (
    -- txn_id: 业务主键或关联键。
    txn_id INTEGER PRIMARY KEY,
    -- wh_id: 业务主键或关联键。
    wh_id TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- inv_txn_type_cd: 业务代码字段，通常需要关联代码表翻译。
    inv_txn_type_cd TEXT NOT NULL,
    -- txn_dt_key: 日期键，文本格式 YYYYMMDD。
    txn_dt_key TEXT NOT NULL,
    -- txn_qty: 数量字段。
    txn_qty INTEGER NOT NULL,
    -- ref_doc_no: 事实记录补充属性字段。
    ref_doc_no TEXT NOT NULL,
    -- txn_uom_cd: 业务代码字段，通常需要关联代码表翻译。
    txn_uom_cd TEXT DEFAULT 'EA',
    -- operator_nm: 操作员相关业务字段。
    operator_nm TEXT DEFAULT 'SYSTEM',
    -- reason_cd: 原因相关业务字段。
    reason_cd TEXT DEFAULT 'NORMAL'
);

-- Table: fact_machine_downtime_evt
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_machine_downtime_evt (
    -- event_id: 业务主键或关联键。
    event_id INTEGER PRIMARY KEY,
    -- prod_line_id: 业务主键或关联键。
    prod_line_id TEXT NOT NULL,
    -- event_dt_key: 日期键，文本格式 YYYYMMDD。
    event_dt_key TEXT NOT NULL,
    -- down_reason_cd: 原因相关业务字段。
    down_reason_cd TEXT NOT NULL,
    -- downtime_min: 时长字段，单位分钟。
    downtime_min REAL NOT NULL,
    -- impact_qty: 数量字段。
    impact_qty INTEGER DEFAULT 0,
    -- maint_team_cd: 业务代码字段，通常需要关联代码表翻译。
    maint_team_cd TEXT DEFAULT 'MTN_A',
    -- severity_cd: 业务代码字段，通常需要关联代码表翻译。
    severity_cd TEXT DEFAULT 'M'
);

-- Table: fact_po_hdr
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_po_hdr (
    -- po_id: 业务主键或关联键。
    po_id TEXT PRIMARY KEY,
    -- supplier_id: 业务主键或关联键。
    supplier_id TEXT NOT NULL,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- po_status_cd: 业务代码字段，通常需要关联代码表翻译。
    po_status_cd TEXT NOT NULL,
    -- po_date_key: 事实记录补充属性字段。
    po_date_key TEXT NOT NULL,
    -- eta_dt_key: 日期键，文本格式 YYYYMMDD。
    eta_dt_key TEXT NOT NULL,
    -- buyer_id: 采购员、采购员编号相关业务字段。
    buyer_id TEXT DEFAULT 'B001',
    -- currency_cd: 业务代码字段，通常需要关联代码表翻译。
    currency_cd TEXT DEFAULT 'CNY',
    -- incoterm_cd: 业务代码字段，通常需要关联代码表翻译。
    incoterm_cd TEXT DEFAULT 'DAP',
    -- approval_status_cd: 业务代码字段，通常需要关联代码表翻译。
    approval_status_cd TEXT DEFAULT 'APR'
);

-- Table: fact_po_line
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_po_line (
    -- po_line_id: 业务主键或关联键。
    po_line_id TEXT PRIMARY KEY,
    -- po_id: 业务主键或关联键。
    po_id TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- po_qty: 数量字段。
    po_qty INTEGER NOT NULL,
    -- recv_qty: 数量字段。
    recv_qty INTEGER NOT NULL,
    -- unit_price_amt: 金额字段。
    unit_price_amt REAL NOT NULL,
    -- tax_amt: 金额字段。
    tax_amt REAL DEFAULT 0,
    -- discount_amt: 金额字段。
    discount_amt REAL DEFAULT 0,
    -- line_eta_dt_key: 日期键，文本格式 YYYYMMDD。
    line_eta_dt_key TEXT DEFAULT '20250101'
);

-- Table: fact_price_book
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_price_book (
    -- price_id: 业务主键或关联键。
    price_id INTEGER PRIMARY KEY,
    -- material_id: 价格记录所属物料编号。
    material_id TEXT NOT NULL,
    -- customer_id: 业务主键或关联键。
    customer_id TEXT,
    -- price_type_cd: 价格类型代码。
    price_type_cd TEXT NOT NULL,
    -- eff_start_dt: 价格生效开始日期，最新价格要取不晚于目标日期的最近记录。
    eff_start_dt TEXT NOT NULL,
    -- eff_end_dt: 价格失效日期。
    eff_end_dt TEXT,
    -- unit_price_amt: 单价金额。
    unit_price_amt REAL NOT NULL,
    -- currency_cd: 业务代码字段，通常需要关联代码表翻译。
    currency_cd TEXT NOT NULL,
    -- min_order_qty: 数量字段。
    min_order_qty INTEGER DEFAULT 1,
    -- price_status_cd: 业务代码字段，通常需要关联代码表翻译。
    price_status_cd TEXT DEFAULT 'ACTIVE',
    -- source_contract_no: 事实记录补充属性字段。
    source_contract_no TEXT DEFAULT 'NA'
);

-- Table: fact_prod_output_dly
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_prod_output_dly (
    -- output_id: 业务主键或关联键。
    output_id INTEGER PRIMARY KEY,
    -- prod_line_id: 产出所属生产线编号。
    prod_line_id TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- output_dt_key: 生产产出日期，文本格式 YYYYMMDD。
    output_dt_key TEXT NOT NULL,
    -- shift_cd: 班次代码。
    shift_cd TEXT NOT NULL,
    -- good_qty: 良品数量。
    good_qty INTEGER NOT NULL,
    -- scrap_qty: 报废数量。
    scrap_qty INTEGER NOT NULL,
    -- runtime_min: 运行时长，单位分钟。
    runtime_min REAL NOT NULL,
    -- rework_qty: 返工数量。
    rework_qty INTEGER DEFAULT 0,
    -- overtime_min: 加班运行时长。
    overtime_min REAL DEFAULT 0,
    -- fp_yield_rate: 一次通过率。
    fp_yield_rate REAL DEFAULT 0.98,
    -- energy_kwh_qty: 产出过程耗电量。
    energy_kwh_qty REAL DEFAULT 0
);

-- Table: fact_qa_defect
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_qa_defect (
    -- qa_defect_id: 业务主键或关联键。
    qa_defect_id INTEGER PRIMARY KEY,
    -- inspection_id: 业务主键或关联键。
    inspection_id TEXT NOT NULL,
    -- defect_type_cd: 业务代码字段，通常需要关联代码表翻译。
    defect_type_cd TEXT NOT NULL,
    -- defect_qty: 数量字段。
    defect_qty INTEGER NOT NULL,
    -- defect_loc_cd: 业务代码字段，通常需要关联代码表翻译。
    defect_loc_cd TEXT DEFAULT 'NA',
    -- root_cause_cd: 根因相关业务字段。
    root_cause_cd TEXT DEFAULT 'TBD',
    -- containment_fg: 布尔标记字段，1/0 表示是或否。
    containment_fg INTEGER DEFAULT 0
);

-- Table: fact_qa_inspection
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_qa_inspection (
    -- inspection_id: 业务主键或关联键。
    inspection_id TEXT PRIMARY KEY,
    -- work_order_id: 业务主键或关联键。
    work_order_id TEXT,
    -- supplier_id: 业务主键或关联键。
    supplier_id TEXT,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- inspection_dt_key: 日期键，文本格式 YYYYMMDD。
    inspection_dt_key TEXT NOT NULL,
    -- inspected_qty: 数量字段。
    inspected_qty INTEGER NOT NULL,
    -- reject_qty: 数量字段。
    reject_qty INTEGER NOT NULL,
    -- inspector_nm: 检验员相关业务字段。
    inspector_nm TEXT DEFAULT 'QA_TEAM',
    -- inspection_type_cd: 业务代码字段，通常需要关联代码表翻译。
    inspection_type_cd TEXT DEFAULT 'IQC',
    -- lot_no: 事实记录补充属性字段。
    lot_no TEXT DEFAULT 'LOT',
    -- sample_size_qty: 数量字段。
    sample_size_qty INTEGER DEFAULT 0
);

-- Table: fact_sales_order_hdr
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_sales_order_hdr (
    -- sales_order_id: 销售订单头编号。
    sales_order_id TEXT PRIMARY KEY,
    -- customer_id: 下单客户编号。
    customer_id TEXT NOT NULL,
    -- order_type_cd: 订单类型代码。
    order_type_cd TEXT NOT NULL,
    -- sales_order_status_cd: 订单状态代码，需要结合代码表判断是否为有效订单。
    sales_order_status_cd TEXT NOT NULL,
    -- order_date_key: 订单日期，文本格式 YYYYMMDD。
    order_date_key TEXT NOT NULL,
    -- req_delv_date_key: 客户要求交付日期，文本格式 YYYYMMDD。
    req_delv_date_key TEXT NOT NULL,
    -- plant_id: 订单履约工厂编号。
    plant_id TEXT NOT NULL,
    -- sales_org_cd: 销售组织代码。
    sales_org_cd TEXT NOT NULL,
    -- currency_cd: 订单币种。
    currency_cd TEXT DEFAULT 'CNY',
    -- biz_unit_cd: 业务单元代码。
    biz_unit_cd TEXT DEFAULT 'BU01',
    -- sales_channel_cd: 销售渠道代码。
    sales_channel_cd TEXT DEFAULT 'DIRECT',
    -- incoterm_cd: 贸易条款代码。
    incoterm_cd TEXT DEFAULT 'DAP',
    -- created_by: 订单来源系统或创建人。
    created_by TEXT DEFAULT 'ERP'
);

-- Table: fact_sales_order_line
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_sales_order_line (
    -- sales_order_line_id: 销售订单行编号。
    sales_order_line_id TEXT PRIMARY KEY,
    -- sales_order_id: 业务主键或关联键。
    sales_order_id TEXT NOT NULL,
    -- material_id: 订单行物料编号。
    material_id TEXT NOT NULL,
    -- order_qty: 订单数量，业务常用口径字段之一。
    order_qty INTEGER NOT NULL,
    -- order_quantity: 订单数量，同义字段，用于考查语义映射。
    order_quantity INTEGER NOT NULL,
    -- net_amt: 订单行净额。
    net_amt REAL NOT NULL,
    -- line_status_cd: 订单行状态代码。
    line_status_cd TEXT NOT NULL,
    -- promise_dt_key: 承诺交付日期。
    promise_dt_key TEXT NOT NULL,
    -- discount_amt: 订单行折扣金额。
    discount_amt REAL DEFAULT 0,
    -- tax_amt: 订单行税额。
    tax_amt REAL DEFAULT 0,
    -- ship_from_wh_id: 默认发货仓编号。
    ship_from_wh_id TEXT DEFAULT 'WH_E_FG',
    -- priority_cd: 订单行优先级代码。
    priority_cd TEXT DEFAULT 'N',
    -- requested_ship_dt_key: 期望发货日期。
    requested_ship_dt_key TEXT DEFAULT '20250101'
);

-- Table: fact_shipment_hdr
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_shipment_hdr (
    -- shipment_id: 业务主键或关联键。
    shipment_id TEXT PRIMARY KEY,
    -- sales_order_id: 业务主键或关联键。
    sales_order_id TEXT NOT NULL,
    -- ship_dt_key: 日期键，文本格式 YYYYMMDD。
    ship_dt_key TEXT NOT NULL,
    -- ship_status_cd: 业务代码字段，通常需要关联代码表翻译。
    ship_status_cd TEXT NOT NULL,
    -- wh_id: 业务主键或关联键。
    wh_id TEXT NOT NULL,
    -- carrier_nm: 承运商相关业务字段。
    carrier_nm TEXT DEFAULT 'SF',
    -- freight_amt: 运费相关业务字段。
    freight_amt REAL DEFAULT 0,
    -- delivery_mode_cd: 业务代码字段，通常需要关联代码表翻译。
    delivery_mode_cd TEXT DEFAULT 'ROAD'
);

-- Table: fact_shipment_line
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_shipment_line (
    -- shipment_line_id: 业务主键或关联键。
    shipment_line_id INTEGER PRIMARY KEY,
    -- shipment_id: 业务主键或关联键。
    shipment_id TEXT NOT NULL,
    -- sales_order_line_id: 业务主键或关联键。
    sales_order_line_id TEXT NOT NULL,
    -- ship_qty: 数量字段。
    ship_qty INTEGER NOT NULL,
    -- pack_qty: 包装相关业务字段。
    pack_qty INTEGER DEFAULT 1,
    -- gross_wt_kg: 毛重相关业务字段。
    gross_wt_kg REAL DEFAULT 1.0,
    -- volume_cbm: 体积相关业务字段。
    volume_cbm REAL DEFAULT 0.1
);

-- Table: fact_supplier_score_mth
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_supplier_score_mth (
    -- score_id: 业务主键或关联键。
    score_id INTEGER PRIMARY KEY,
    -- supplier_id: 月度评分所属供应商编号。
    supplier_id TEXT NOT NULL,
    -- month_key: 评分月份，文本格式 YYYYMM。
    month_key TEXT NOT NULL,
    -- on_time_rate: 准时交付率。
    on_time_rate REAL NOT NULL,
    -- ppm_defect: 不良 PPM 指标。
    ppm_defect REAL NOT NULL,
    -- score_total: 月度综合评分。
    score_total REAL NOT NULL,
    -- audit_score: 审核相关业务字段。
    audit_score REAL DEFAULT 85,
    -- response_score: 响应相关业务字段。
    response_score REAL DEFAULT 88,
    -- capacity_score: 产能相关业务字段。
    capacity_score REAL DEFAULT 86
);

-- Table: fact_work_order
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_work_order (
    -- work_order_id: 工单编号。
    work_order_id TEXT PRIMARY KEY,
    -- material_id: 工单生产物料编号。
    material_id TEXT NOT NULL,
    -- prod_line_id: 工单执行产线编号。
    prod_line_id TEXT NOT NULL,
    -- work_order_status_cd: 工单状态代码。
    work_order_status_cd TEXT NOT NULL,
    -- plan_start_dt_key: 计划开始日期。
    plan_start_dt_key TEXT NOT NULL,
    -- actual_end_dt_key: 实际结束日期。
    actual_end_dt_key TEXT,
    -- planned_qty: 计划数量。
    planned_qty INTEGER NOT NULL,
    -- completed_qty: 完工数量。
    completed_qty INTEGER NOT NULL,
    -- source_sales_order_id: 来源销售订单编号。
    source_sales_order_id TEXT,
    -- work_center_cd: 业务代码字段，通常需要关联代码表翻译。
    work_center_cd TEXT DEFAULT 'ASM',
    -- release_dt_key: 日期键，文本格式 YYYYMMDD。
    release_dt_key TEXT DEFAULT '20250101',
    -- close_dt_key: 日期键，文本格式 YYYYMMDD。
    close_dt_key TEXT,
    -- yield_loss_qty: 数量字段。
    yield_loss_qty INTEGER DEFAULT 0,
    -- priority_cd: 业务代码字段，通常需要关联代码表翻译。
    priority_cd TEXT DEFAULT 'N'
);

-- Table: fact_work_order_opr
-- 事实表，记录交易、库存、生产、质量或过程数据。
CREATE TABLE fact_work_order_opr (
    -- opr_id: 业务主键或关联键。
    opr_id INTEGER PRIMARY KEY,
    -- work_order_id: 业务主键或关联键。
    work_order_id TEXT NOT NULL,
    -- opr_seq: 顺序号字段。
    opr_seq INTEGER NOT NULL,
    -- work_center_cd: 业务代码字段，通常需要关联代码表翻译。
    work_center_cd TEXT NOT NULL,
    -- std_cycle_min: 时长字段，单位分钟。
    std_cycle_min REAL NOT NULL,
    -- actual_cycle_min: 时长字段，单位分钟。
    actual_cycle_min REAL NOT NULL,
    -- setup_min: 换型准备相关业务字段。
    setup_min REAL DEFAULT 0,
    -- wait_min: 等待相关业务字段。
    wait_min REAL DEFAULT 0,
    -- opr_status_cd: 业务代码字段，通常需要关联代码表翻译。
    opr_status_cd TEXT DEFAULT 'CMP'
);

-- Table: wide_after_sale_case
-- 宽表，聚合多个业务主题字段，故意提高 NL2SQL 取数复杂度。
CREATE TABLE wide_after_sale_case (
    -- case_id: 售后案例编号。
    case_id TEXT PRIMARY KEY,
    -- customer_id: 业务主键或关联键。
    customer_id TEXT NOT NULL,
    -- sales_order_id: 业务主键或关联键。
    sales_order_id TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- open_dt_key: 售后案例创建日期。
    open_dt_key TEXT NOT NULL,
    -- close_dt_key: 售后案例关闭日期。
    close_dt_key TEXT,
    -- case_type_cd: 业务代码字段，通常需要关联代码表翻译。
    case_type_cd TEXT NOT NULL,
    -- case_status_cd: 售后案例状态代码。
    case_status_cd TEXT NOT NULL,
    -- severity_cd: 业务代码字段，通常需要关联代码表翻译。
    severity_cd TEXT NOT NULL,
    -- resp_team_cd: 业务代码字段，通常需要关联代码表翻译。
    resp_team_cd TEXT NOT NULL,
    -- issue_channel_cd: 业务代码字段，通常需要关联代码表翻译。
    issue_channel_cd TEXT NOT NULL,
    -- root_cause_cd: 根因相关业务字段。
    root_cause_cd TEXT NOT NULL,
    -- claim_amt: 售后索赔金额。
    claim_amt REAL NOT NULL,
    -- replace_qty: 数量字段。
    replace_qty INTEGER NOT NULL,
    -- return_qty: 数量字段。
    return_qty INTEGER NOT NULL,
    -- onsite_visit_fg: 布尔标记字段，1/0 表示是或否。
    onsite_visit_fg INTEGER NOT NULL,
    -- reopen_fg: 布尔标记字段，1/0 表示是或否。
    reopen_fg INTEGER NOT NULL,
    -- sat_score: 评分字段。
    sat_score REAL NOT NULL,
    -- first_resp_hour: 宽表分析字段，用于直接支持查询与洞察。
    first_resp_hour REAL NOT NULL,
    -- close_sla_hit_fg: 布尔标记字段，1/0 表示是或否。
    close_sla_hit_fg INTEGER NOT NULL,
    -- final_action_cd: 业务代码字段，通常需要关联代码表翻译。
    final_action_cd TEXT NOT NULL
);

-- Table: wide_order_fulfillment_dly
-- 宽表，聚合多个业务主题字段，故意提高 NL2SQL 取数复杂度。
CREATE TABLE wide_order_fulfillment_dly (
    -- row_id: 业务主键或关联键。
    row_id INTEGER PRIMARY KEY,
    -- sales_order_id: 履约宽表对应销售订单编号。
    sales_order_id TEXT NOT NULL,
    -- sales_order_line_id: 履约宽表对应订单行编号。
    sales_order_line_id TEXT NOT NULL,
    -- order_date_key: 宽表分析字段，用于直接支持查询与洞察。
    order_date_key TEXT NOT NULL,
    -- customer_id: 业务主键或关联键。
    customer_id TEXT NOT NULL,
    -- customer_region_cd: 业务代码字段，通常需要关联代码表翻译。
    customer_region_cd TEXT NOT NULL,
    -- customer_segment_cd: 业务代码字段，通常需要关联代码表翻译。
    customer_segment_cd TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- prod_family_cd: 业务代码字段，通常需要关联代码表翻译。
    prod_family_cd TEXT NOT NULL,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- wh_id: 业务主键或关联键。
    wh_id TEXT NOT NULL,
    -- order_qty: 数量字段。
    order_qty INTEGER NOT NULL,
    -- allocated_qty: 数量字段。
    allocated_qty INTEGER NOT NULL,
    -- shipped_qty: 数量字段。
    shipped_qty INTEGER NOT NULL,
    -- backlog_qty: 未完成交付数量，常用于延期和风险分析。
    backlog_qty INTEGER NOT NULL,
    -- unit_price_amt: 金额字段。
    unit_price_amt REAL NOT NULL,
    -- net_amt: 金额字段。
    net_amt REAL NOT NULL,
    -- promise_dt_key: 日期键，文本格式 YYYYMMDD。
    promise_dt_key TEXT NOT NULL,
    -- actual_ship_dt_key: 日期键，文本格式 YYYYMMDD。
    actual_ship_dt_key TEXT,
    -- on_time_flag: 是否按时交付标记。
    on_time_flag INTEGER NOT NULL,
    -- order_status_cd: 业务代码字段，通常需要关联代码表翻译。
    order_status_cd TEXT NOT NULL,
    -- delivery_risk_cd: 履约风险等级代码。
    delivery_risk_cd TEXT NOT NULL
);

-- Table: wide_prod_line_hourly_board
-- 宽表，聚合多个业务主题字段，故意提高 NL2SQL 取数复杂度。
CREATE TABLE wide_prod_line_hourly_board (
    -- row_id: 业务主键或关联键。
    row_id INTEGER PRIMARY KEY,
    -- prod_line_id: 业务主键或关联键。
    prod_line_id TEXT NOT NULL,
    -- workshop_id: 业务主键或关联键。
    workshop_id TEXT NOT NULL,
    -- plant_id: 业务主键或关联键。
    plant_id TEXT NOT NULL,
    -- board_dt_key: 小时看板业务日期。
    board_dt_key TEXT NOT NULL,
    -- shift_cd: 业务代码字段，通常需要关联代码表翻译。
    shift_cd TEXT NOT NULL,
    -- hour_bucket_cd: 小时桶编码。
    hour_bucket_cd TEXT NOT NULL,
    -- material_id: 业务主键或关联键。
    material_id TEXT NOT NULL,
    -- plan_qty: 数量字段。
    plan_qty INTEGER NOT NULL,
    -- good_qty: 数量字段。
    good_qty INTEGER NOT NULL,
    -- scrap_qty: 数量字段。
    scrap_qty INTEGER NOT NULL,
    -- rework_qty: 数量字段。
    rework_qty INTEGER NOT NULL,
    -- runtime_min: 时长字段，单位分钟。
    runtime_min REAL NOT NULL,
    -- downtime_min: 时长字段，单位分钟。
    downtime_min REAL NOT NULL,
    -- setup_min: 换型准备相关业务字段。
    setup_min REAL NOT NULL,
    -- fp_yield_rate: 比率指标。
    fp_yield_rate REAL NOT NULL,
    -- oee_rate: 产线综合设备效率指标。
    oee_rate REAL NOT NULL,
    -- takt_sec: 节拍、秒相关业务字段。
    takt_sec REAL NOT NULL,
    -- headcount_qty: 数量字段。
    headcount_qty INTEGER NOT NULL,
    -- energy_kwh_qty: 耗电量相关业务字段。
    energy_kwh_qty REAL NOT NULL,
    -- quality_alert_fg: 质量预警标记。
    quality_alert_fg INTEGER NOT NULL,
    -- bottleneck_reason_cd: 原因相关业务字段。
    bottleneck_reason_cd TEXT NOT NULL
);
