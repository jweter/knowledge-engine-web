"""Application configuration.

This project reads `knowledge-engine-core`'s SQLite database read-only --
see `docs/web_design.md`'s Decision section for why that is a database
connection, not a Python import of `knowledge_engine`. Kept in one small
object, mirroring `core`'s own `knowledge_engine.config.Settings`, but
under this project's own `KE_WEB_` prefix -- this is a distinct
consuming process, not `core` itself.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for Knowledge Engine Web."""

    database_url: str = "sqlite:///data/knowledge_engine.sqlite3"
    evidence_records_path: str | None = None
    relationship_records_path: str | None = None
    whats_changed_baseline_path: str = "data/whats_changed_baseline.json"
    snapshot_metadata_path: str = "data/snapshot_metadata.json"
    host: str = "127.0.0.1"
    port: int = 8000
    alpha_username: str | None = None
    alpha_password: str | None = None
    llm_model: str | None = None
    ollama_host: str = "http://127.0.0.1:11434"
    # AI-O13/AI-O14: Research Copilot needs corpus metadata, a durable
    # session store, and core's CLI in addition to the existing evidence
    # path and Ollama settings. Web retrieval itself still reads core's
    # SQLite database directly and does not depend on these settings.
    sources_path: str | None = None
    session_db_path: str = "data/research_sessions.db"
    session_storage_mode: Literal["local", "persistent"] = "local"
    session_persistent_root: str | None = None
    ke_executable: str = "ke"

    model_config = SettingsConfigDict(env_prefix="KE_WEB_", env_file=".env", extra="ignore")
