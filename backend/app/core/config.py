"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # === SiliconFlow API (OpenAI-compatible) ===
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # === Main LLM ===
    llm_model_name: str = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_request_timeout: int = 60
    llm_retry_attempts: int = 1
    llm_retry_backoff_seconds: float = 1.5

    # === Embedding: BAAI/bge-m3 (via SiliconFlow) ===
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_api_key: str = ""
    enable_embedding_retrieval: bool = False

    # === Qdrant semantic context retrieval ===
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "nl2sql_context"
    enable_qdrant_retrieval: bool = True
    qdrant_top_k: int = 8
    qdrant_score_threshold: float = 0.35

    # === Reranker: BAAI/bge-reranker-v2-m3 (via SiliconFlow API) ===
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_api_key: str = ""
    enable_reranker: bool = False

    # === Supervisor / Reflection LLM: Aliyun Bailian OpenAI-compatible API ===
    scopedashboard_api_key: str = ""
    scopedashboard_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    scopedashboard_model: str = "qwen3.5-35b-a3b"
    scopedashboard_temperature: float = 0
    scopedashboard_request_timeout: int = 30

    # === Few-shot Example Store ===
    example_store_path: str = "data/knowledge/few_shots.json"
    example_retrieval_top_k: int = 3
    enable_template_reuse: bool = False
    template_reuse_threshold: float = 0.95

    # === Database (SQLite for MVP) ===
    database_url: str = "sqlite:///./data/nl2sql.db"

    # === App ===
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    debug: bool = True
    app_reload: bool = True
    trace_level: str = "normal"
    enable_empty_result_diagnosis: bool = True
    enable_value_resolver: bool = True
    enable_model_planner: bool = False

    # === Security ===
    allowed_tables: str = ""
    query_timeout: int = 30

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        """Accept common deployment-style DEBUG values from the shell."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @field_validator("trace_level")
    @classmethod
    def validate_trace_level(cls, value: str) -> str:
        normalized = (value or "normal").strip().lower()
        if normalized not in {"lite", "normal", "debug"}:
            return "normal"
        return normalized

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Resolve relative SQLite URLs from the backend directory, not the shell cwd."""
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value

        raw_path = value[len(prefix) :]
        path = Path(raw_path)
        if path.is_absolute():
            return value
        return prefix + (BACKEND_DIR / path).resolve().as_posix()

    @field_validator("example_store_path")
    @classmethod
    def normalize_example_store_path(cls, value: str) -> str:
        """Resolve few-shot store path from the backend directory."""
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str((BACKEND_DIR / path).resolve())

    class Config:
        env_file = str(BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
