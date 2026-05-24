# Manufacturing NL2SQL Preliminary Dataset

- Domain: manufacturing and supply chain
- Format: CSV
- Includes code tables, wide tables, EAV attributes, and text date keys

## Hidden Rule Hints

- `有效订单` should exclude rows where `code_sales_order_status.is_valid_order = 0`.
- `最新价格` should use the latest `eff_start_dt` not later than the target date.
- `可用库存 = on_hand_qty - alloc_qty`.
- Date keys use `YYYYMMDD` text format.