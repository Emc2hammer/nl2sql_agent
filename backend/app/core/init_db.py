"""Initialize the local SQLite database from the competition dataset."""

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BACKEND_DIR / "data" / "nl2sqlpublic" / "public"
SCHEMA_PATH = DATASET_DIR / "schema_annotated.sql"
CSV_DIR = DATASET_DIR / "csv"


def init_database() -> None:
    """Create competition tables and load all bundled CSV data into SQLite."""
    from sqlalchemy import inspect as sa_inspect

    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {},
    )

    expected_tables = _csv_table_names()
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if expected_tables and expected_tables.issubset(existing_tables):
        logger.info("Competition database already initialized (%s tables)", len(existing_tables))
        engine.dispose()
        return

    if existing_tables:
        logger.info("Existing non-competition database detected; rebuilding local SQLite data.")

    if not settings.database_url.startswith("sqlite"):
        raise RuntimeError("Competition CSV initialization currently supports SQLite only.")

    db_path = _sqlite_path_from_url(settings.database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing SQLite database from %s", DATASET_DIR)
    raw_conn = sqlite3.connect(db_path)
    try:
        _drop_existing_tables(raw_conn)
        _create_schema(raw_conn)
        _load_csv_files(raw_conn)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()
        engine.dispose()

    logger.info("Competition database initialized successfully.")


def _sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported SQLite URL: {database_url}")

    raw_path = database_url[len(prefix) :]
    path = Path(raw_path)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def _csv_table_names() -> set[str]:
    if not CSV_DIR.exists():
        raise FileNotFoundError(f"CSV dataset directory not found: {CSV_DIR}")
    return {path.stem for path in CSV_DIR.glob("*.csv")}


def _drop_existing_tables(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.execute("PRAGMA foreign_keys = OFF")
    for (table_name,) in rows:
        if table_name.startswith("sqlite_"):
            continue
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')


def _create_schema(conn: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _load_csv_files(conn: sqlite3.Connection) -> None:
    csv_paths = sorted(CSV_DIR.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found in {CSV_DIR}")

    for csv_path in csv_paths:
        table_name = csv_path.stem
        inserted = _load_csv_file(conn, table_name, csv_path)
        logger.info("Loaded %s rows into %s", inserted, table_name)


def _load_csv_file(conn: sqlite3.Connection, table_name: str, csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0

        columns = reader.fieldnames
        quoted_columns = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})'

        batch = []
        total = 0
        for row in reader:
            batch.append(tuple(_normalize_csv_value(row.get(col)) for col in columns))
            if len(batch) >= 1000:
                conn.executemany(sql, batch)
                total += len(batch)
                batch.clear()

        if batch:
            conn.executemany(sql, batch)
            total += len(batch)

    return total


def _normalize_csv_value(value: Optional[str]) -> Optional[str]:
    if value == "":
        return None
    return value
