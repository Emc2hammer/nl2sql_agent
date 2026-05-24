"""Query service - executes SQL queries against the database."""

import time
import traceback
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings


class QueryService:
    """Service to execute validated SQL queries and return results."""

    def __init__(self):
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
        )

    def execute_query(self, sql: str) -> dict:
        """
        Execute a SQL query and return results.

        Args:
            sql: The SQL query to execute.

        Returns:
            Dict with 'rows', 'columns', 'error', and 'execution_time'.
        """
        start_time = time.time()
        result = {
            "rows": [],
            "columns": [],
            "error": None,
            "execution_time": 0.0,
        }

        try:
            with self.engine.connect() as conn:
                # SQLite doesn't support SET statement_timeout
                if not settings.database_url.startswith("sqlite"):
                    conn.execute(
                        text(f"SET statement_timeout = {settings.query_timeout * 1000}")
                    )

                db_result = conn.execute(text(sql))

                # Get column names
                result["columns"] = list(db_result.keys())

                # Fetch rows (limited)
                rows = db_result.fetchmany(200)
                result["rows"] = [dict(row._mapping) for row in rows]

        except SQLAlchemyError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}\n{traceback.format_exc()}"

        result["execution_time"] = round(time.time() - start_time, 3)
        return result
