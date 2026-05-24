"""Database connection management using SQLAlchemy (SQLite for MVP)."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# SQLite needs check_same_thread=False for FastAPI multi-thread access
_engine_args = {}
if settings.database_url.startswith("sqlite"):
    _engine_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=_engine_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_table_schema(db_url: str = None) -> list[dict]:
    """
    Inspect the database and return schema information for all tables.
    Returns a list of dicts with table_name, columns, and sample data.
    """
    from sqlalchemy import inspect as sa_inspect

    url = db_url or settings.database_url
    eng = create_engine(url)
    inspector = sa_inspect(eng)
    schema_info = []

    for table_name in inspector.get_table_names():
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": col.get("primary_key", False),
                "default": str(col.get("default", "")),
            })

        # Get sample rows (up to 3)
        sample_rows = []
        try:
            with eng.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM \"{table_name}\" LIMIT 3"))
                sample_rows = [dict(row._mapping) for row in result]
        except Exception:
            pass

        schema_info.append({
            "table_name": table_name,
            "columns": columns,
            "sample_rows": sample_rows,
        })

    eng.dispose()
    return schema_info
