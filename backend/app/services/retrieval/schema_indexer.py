"""Load lightweight schema metadata used by context retrievers."""

import csv
from dataclasses import dataclass, field
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BACKEND_DIR / "data" / "nl2sqlpublic" / "public"
TABLE_DICTIONARY_PATH = DATASET_DIR / "table_dictionary.csv"


TABLE_DESCRIPTIONS: dict[str, str] = {
    "bridge_bom_component": "BOM component bridge table",
    "code_defect_type": "defect type code table",
    "code_inv_txn_type": "inventory transaction type code table",
    "code_order_type": "sales order type code table",
    "code_sales_order_status": "sales order status code table with valid order flag",
    "code_supplier_class": "supplier class code table",
    "code_uom": "unit of measure code table",
    "code_work_order_status": "work order status code table",
    "dim_bin_loc": "warehouse bin location dimension",
    "dim_bom_hdr": "BOM header dimension",
    "dim_calendar_mth": "month calendar dimension",
    "dim_customer": "customer master dimension",
    "dim_customer_addr": "customer address dimension",
    "dim_customer_profile": "customer profile dimension",
    "dim_material": "material and product master dimension",
    "dim_material_alias": "material alias dimension",
    "dim_plant": "plant dimension",
    "dim_prod_line": "production line dimension",
    "dim_shift": "shift dimension",
    "dim_supplier": "supplier master dimension",
    "dim_supplier_profile": "supplier profile dimension",
    "dim_wh": "warehouse dimension",
    "dim_workshop": "workshop dimension",
    "eav_material_attr": "material flexible attributes such as color and voltage",
    "fact_energy_usage_dly": "daily energy usage fact",
    "fact_forecast_mth": "monthly forecast fact",
    "fact_inv_balance_snap": "inventory balance snapshot fact",
    "fact_inv_txn": "inventory transaction fact",
    "fact_machine_downtime_evt": "machine downtime event fact",
    "fact_po_hdr": "purchase order header fact",
    "fact_po_line": "purchase order line fact",
    "fact_price_book": "material price book fact",
    "fact_prod_output_dly": "daily production output fact",
    "fact_qa_defect": "quality defect fact",
    "fact_qa_inspection": "quality inspection fact",
    "fact_sales_order_hdr": "sales order header fact",
    "fact_sales_order_line": "sales order line fact",
    "fact_shipment_hdr": "shipment header fact",
    "fact_shipment_line": "shipment line fact",
    "fact_supplier_score_mth": "monthly supplier score fact",
    "fact_work_order": "work order fact",
    "fact_work_order_opr": "work order operation fact",
    "wide_after_sale_case": "wide after-sales service case table",
    "wide_order_fulfillment_dly": "wide daily order fulfillment table",
    "wide_prod_line_hourly_board": "wide production line hourly board table",
}


DOMAIN_TABLES: dict[str, list[str]] = {
    "sales": [
        "wide_order_fulfillment_dly",
        "fact_sales_order_hdr",
        "fact_sales_order_line",
        "dim_customer",
        "dim_customer_profile",
        "code_sales_order_status",
        "code_order_type",
        "fact_shipment_hdr",
        "fact_shipment_line",
        "dim_material",
    ],
    "product": [
        "dim_material",
        "eav_material_attr",
        "dim_material_alias",
        "dim_bom_hdr",
        "bridge_bom_component",
        "fact_price_book",
        "dim_customer",
    ],
    "production": [
        "wide_prod_line_hourly_board",
        "fact_prod_output_dly",
        "fact_work_order",
        "fact_work_order_opr",
        "dim_prod_line",
        "dim_workshop",
        "dim_plant",
        "dim_shift",
        "code_work_order_status",
    ],
    "quality": [
        "fact_qa_inspection",
        "fact_qa_defect",
        "code_defect_type",
        "fact_work_order",
        "dim_material",
        "dim_supplier",
    ],
    "inventory": [
        "fact_inv_balance_snap",
        "fact_inv_txn",
        "fact_forecast_mth",
        "dim_material",
        "dim_wh",
        "dim_bin_loc",
        "code_inv_txn_type",
    ],
    "supplier": [
        "dim_supplier",
        "dim_supplier_profile",
        "fact_supplier_score_mth",
        "fact_po_hdr",
        "fact_po_line",
        "fact_qa_inspection",
        "dim_material",
        "code_supplier_class",
    ],
    "after_sales": [
        "wide_after_sale_case",
        "fact_sales_order_hdr",
        "dim_customer",
        "dim_material",
        "dim_plant",
    ],
}


@dataclass
class ColumnDoc:
    """Dictionary metadata for one column."""

    name: str
    description: str


@dataclass
class TableDoc:
    """Searchable schema document for one table."""

    name: str
    description: str = ""
    columns: dict[str, ColumnDoc] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        parts = [self.name, self.description]
        for col in self.columns.values():
            parts.extend([col.name, col.description])
        return " ".join(parts).lower()


class SchemaIndex:
    """In-memory schema index backed by the bundled table dictionary."""

    def __init__(self) -> None:
        self.tables = self._load_tables()

    def _load_tables(self) -> dict[str, TableDoc]:
        tables: dict[str, TableDoc] = {
            name: TableDoc(name=name, description=desc)
            for name, desc in TABLE_DESCRIPTIONS.items()
        }
        if not TABLE_DICTIONARY_PATH.exists():
            return tables

        with TABLE_DICTIONARY_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                table_name = row["table_name"]
                column_name = row["column_name"]
                description = row["column_description"]
                table = tables.setdefault(
                    table_name,
                    TableDoc(name=table_name, description=TABLE_DESCRIPTIONS.get(table_name, "")),
                )
                table.columns[column_name] = ColumnDoc(column_name, description)
        return tables

    def candidate_tables(self, domain: str) -> list[str]:
        if domain in DOMAIN_TABLES:
            return DOMAIN_TABLES[domain]
        return list(self.tables.keys())
