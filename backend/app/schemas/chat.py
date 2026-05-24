"""Pydantic schemas for request/response models."""

from pydantic import BaseModel, Field
from typing import Optional, Union


class ChatRequest(BaseModel):
    """Request schema for natural language to SQL query."""
    question: str = Field(..., min_length=1, max_length=1000, description="Natural language question")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID for context")


class ChatResponse(BaseModel):
    """Response schema for the NL2SQL result."""
    trace_id: str = ""
    question: str
    sql: str
    result: Union[list[dict], str]
    columns: list[str] = []
    execution_time: float = 0.0
    error: Optional[str] = None
    generated_sql: str = ""
    explanation: str = ""
    insights: list[str] = []


class ValidateSQLRequest(BaseModel):
    """Request schema for SQL validation."""
    sql: str = Field(..., description="SQL query to validate")


class ValidateSQLResponse(BaseModel):
    """Response schema for SQL validation."""
    valid: bool
    message: str
    risk_level: str = "safe"  # safe, warning, dangerous


class TableSchemaResponse(BaseModel):
    """Response schema for table schema info."""
    tables: list[dict]
