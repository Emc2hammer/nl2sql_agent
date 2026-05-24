"""SQL Guard service - validates and sanitizes SQL queries."""

import re
from app.core.config import settings


class SQLGuard:
    """Validates SQL queries for safety and correctness."""

    # Dangerous keywords that should be blocked
    DESTRUCTIVE_KEYWORDS = [
        "DROP", "ALTER", "TRUNCATE", "DELETE", "INSERT",
        "UPDATE", "CREATE", "REPLACE", "EXEC", "EXECUTE",
        "GRANT", "REVOKE", "CALL",
    ]

    # Risky operations that should warn
    RISKY_PATTERNS = [
        (r"\' OR \'1\'=\'1", "SQL injection pattern detected"),
        (r"\' --", "SQL injection pattern detected"),
        (r"\/\*", "Comment injection detected"),
        (r"UNION\s+ALL\s+SELECT", "UNION injection possible"),
        (r"UNION\s+SELECT", "UNION injection possible"),
        (r"INTO\s+OUTFILE", "File write operation"),
        (r"INTO\s+DUMPFILE", "File write operation"),
        (r"LOAD\s+FILE", "File read operation"),
        (r"PG_SLEEP", "Time-based detection"),
        (r"WAITFOR\s+DELAY", "Time-based detection"),
    ]

    def __init__(self):
        self.allowed_tables = set()
        if settings.allowed_tables:
            self.allowed_tables = set(
                t.strip().lower() for t in settings.allowed_tables.split(",") if t.strip()
            )

    def validate(self, sql: str) -> tuple[bool, str, str]:
        """
        Validate a SQL query for safety.

        Args:
            sql: The SQL query to validate.

        Returns:
            Tuple of (is_valid, message, risk_level).
        """
        sql_upper = sql.upper().strip()

        # Check for destructive keywords
        for keyword in self.DESTRUCTIVE_KEYWORDS:
            # Check if keyword appears as a whole word
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                return False, f"Destructive operation detected: {keyword}", "dangerous"

        # Check for risky patterns
        for pattern, message in self.RISKY_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return False, message, "dangerous"

        # Check table restrictions
        if self.allowed_tables:
            # Extract table names from FROM/JOIN clauses
            table_refs = re.findall(
                r'(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                sql,
                re.IGNORECASE,
            )
            for table in table_refs:
                table_clean = table.strip('"').lower()
                if table_clean not in self.allowed_tables:
                    return (
                        False,
                        f"Table '{table_clean}' is not in the allowed tables list",
                        "dangerous",
                    )

        return True, "SQL query passed validation", "safe"

    def get_allowed_tables_summary(self) -> str:
        """Get a summary of allowed tables for display."""
        if self.allowed_tables:
            return f"Allowed tables: {', '.join(sorted(self.allowed_tables))}"
        return "All tables are allowed (no restrictions)"
