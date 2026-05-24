"""Retrieve join paths from the competition relationship map."""

import csv
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
RELATIONSHIP_MAP_PATH = BACKEND_DIR / "data" / "nl2sqlpublic" / "public" / "relationship_map.csv"


@dataclass(frozen=True)
class JoinPath:
    """A join edge from relationship_map.csv."""

    from_column: str
    to_column: str
    cardinality: str

    @property
    def tables(self) -> set[str]:
        return {self.from_column.split(".")[0], self.to_column.split(".")[0]}

    def as_sql_hint(self) -> str:
        return f"{self.from_column} = {self.to_column} ({self.cardinality})"


class JoinRetriever:
    """Retrieve relationship edges relevant to selected tables."""

    def __init__(self) -> None:
        self.joins = self._load_joins()

    def retrieve(self, table_names: list[str], max_joins: int = 8) -> list[JoinPath]:
        selected = set(table_names)
        direct = [join for join in self.joins if join.tables.issubset(selected)]
        bridge = [
            join for join in self.joins
            if join not in direct and len(join.tables & selected) == 1
        ]
        return (direct + bridge)[:max_joins]

    def _load_joins(self) -> list[JoinPath]:
        if not RELATIONSHIP_MAP_PATH.exists():
            return []
        with RELATIONSHIP_MAP_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [
                JoinPath(
                    from_column=row["from_column"],
                    to_column=row["to_column"],
                    cardinality=row["cardinality"],
                )
                for row in reader
            ]
