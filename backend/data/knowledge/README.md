# NL2SQL Knowledge Base

This folder stores local retrieval knowledge for the competition dataset.

- `business_rules.json`: implicit business rules such as valid orders, latest prices, available inventory, current BOM.
- `sql_patterns.json`: reusable SQL reasoning patterns such as TopN, grouped TopN, period-over-period comparison, latest record.
- `few_shots.json`: curated natural-language question to correct SQL examples.

Schema knowledge comes from `data/nl2sqlpublic/public/table_dictionary.csv` plus live SQLite schema inspection.
Join knowledge comes from `data/nl2sqlpublic/public/relationship_map.csv`.
