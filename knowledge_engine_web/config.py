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

    model_config = SettingsConfigDict(env_prefix="KE_WEB_", env_file=".env", extra="ignore")
