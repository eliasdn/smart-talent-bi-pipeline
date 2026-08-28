"""Application configuration module using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for the talent analytics pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///data/output/talent_bi.db",
        description="Database connection URL",
    )
    raw_data_dir: Path = Field(
        default=Path("data/raw"),
        description="Directory containing raw JSON and CSV source files",
    )
    output_dir: Path = Field(
        default=Path("data/output"),
        description="Directory for generated database and output files",
    )
    reports_dir: Path = Field(
        default=Path("data/output/reports"),
        description="Directory for generated report documents",
    )
    log_level: str = Field(
        default="INFO",
        description="Application logging verbosity level",
    )
    debug: bool = Field(
        default=False,
        description="Toggle debug flag for detailed tracing",
    )

    def ensure_directories(self) -> None:
        """Create configured directory paths if they do not exist."""
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve and cache application settings singleton."""
    settings = Settings()
    settings.ensure_directories()
    return settings
