"""Application configuration.

This project reads `knowledge-engine-core`'s SQLite database read-only --
see `docs/web_design.md`'s Decision section for why that is a database
connection, not a Python import of `knowledge_engine`. Kept in one small
object, mirroring `core`'s own `knowledge_engine.config.Settings`, but
under this project's own `KE_WEB_` prefix -- this is a distinct
consuming process, not `core` itself.
"""

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
    # AI-O13: `run_research_question`'s two new inputs, under this
    # project's own KE_WEB_ namespace like everything else here --
    # `llm_model`/`ollama_host` above are reused as-is since one Ollama
    # host and model already serves this process's own `/ask
    # synthesize=1` path. `sources_path` is genuinely new: this project
    # has never needed a `sources.csv` before (its own retrieval reads
    # `core`'s SQLite database directly), but `ke evidence-report`
    # (what `knowledge_engine_ai`'s retrieval shells out to) requires
    # one alongside the evidence file.
    sources_path: str | None = None
    session_db_path: str = "data/research_sessions.db"

    model_config = SettingsConfigDict(env_prefix="KE_WEB_", env_file=".env", extra="ignore")
