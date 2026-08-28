"""Application configuration.

This project reads `knowledge-engine-core`'s SQLite database read-only --
see `docs/web_design.md`'s Decision section for why that is a database
connection, not a Python import of `knowledge_engine`. Kept in one small
object, mirroring `core`'s own `knowledge_engine.config.Settings`, but
under this project's own `KE_WEB_` prefix -- this is a distinct
consuming process, not `core` itself.
"""

from typing import Literal

from pydantic import Field
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
    # Hosted deployments may require a stronger readiness check than merely
    # finding an executable on PATH. When enabled, Web verifies that the
    # configured Core CLI exposes every command Research Copilot can invoke.
    # Kept off by default for local/test compatibility; Render turns it on.
    core_cli_command_preflight: bool = False
    ai_request_timeout_seconds: float = Field(default=180.0, gt=0)
    ai_max_concurrent_requests: int = Field(default=1, gt=0)
    ai_rate_limit_requests: int = Field(default=3, gt=0)
    ai_rate_limit_window_seconds: float = Field(default=600.0, gt=0)
    # GQR-4/GQR-5: Research mode may acquire accessible full text before
    # grounded extraction. This directory is a durable product input/output,
    # not a cache: an acquired Paper may be reused by later research runs.
    research_papers_dir: str = "data/research_papers"
    # Federated discovery (WEB-FRD-1): a second, separate opt-in feature that
    # also calls `ke` and real scholarly-provider HTTPS APIs. Kept on its own
    # budget/guard rather than sharing the Research Copilot settings above so
    # the two features cannot starve each other's concurrency/rate-limit slots.
    federated_discovery_ledger_root: str = "data/federated_discovery_runs"
    federated_openalex_api_key: str | None = None
    federated_semantic_scholar_api_key: str | None = None
    discovery_request_timeout_seconds: float = Field(default=60.0, gt=0)
    discovery_max_concurrent_requests: int = Field(default=1, gt=0)
    discovery_rate_limit_requests: int = Field(default=5, gt=0)
    discovery_rate_limit_window_seconds: float = Field(default=600.0, gt=0)
    # WEB-FRD-5 (research freshness history), item 6: the federated-discovery
    # ledger needs the same local/persistent split AI-O15 already established
    # for Research Session storage, or "return later and see what changed"
    # silently stops being true on every Render redeploy. Mirrors
    # session_storage_mode/session_persistent_root exactly; a separate
    # setting because the ledger and the session store are independent
    # durable stores with independent operator opt-in.
    discovery_ledger_storage_mode: Literal["local", "persistent"] = "local"
    discovery_ledger_persistent_root: str | None = None

    model_config = SettingsConfigDict(env_prefix="KE_WEB_", env_file=".env", extra="ignore")
