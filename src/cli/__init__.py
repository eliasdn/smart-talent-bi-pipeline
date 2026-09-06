"""CLI application and pipeline orchestration package."""

from typing import Any

__all__ = [
    "app",
    "main",
    "PipelineOrchestrator",
    "IngestionResult",
    "MatchingResult",
    "ReportingResult",
    "PipelineSummary",
    "VerificationCheckResult",
    "run_pipeline_verification",
]


def __getattr__(name: str) -> Any:
    """Lazy-load CLI components on access to avoid circular imports during module execution."""
    if name in __all__:
        import src.cli.main as cli_main
        return getattr(cli_main, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
