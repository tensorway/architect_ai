"""Environment and settings helpers for the LangChain agent proof of concept."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[0]
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
DEFAULT_MODEL_PROVIDER = "openai"
DEFAULT_WORKFLOW_LOG_FILE = PROJECT_ROOT / f"agent/logging/{uuid4()}.log"
DEFAULT_WORKFLOW_REPORT_FILE = "workflow_log.html"


class ModelStrength(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _resolve_project_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


@dataclass(slots=True)
class Settings:
    model_api_key: str
    model_name: str = DEFAULT_MODEL_NAME
    model_provider: str = DEFAULT_MODEL_PROVIDER
    workflow_log_file: str = str(DEFAULT_WORKFLOW_LOG_FILE)
    workflow_report_file: str = DEFAULT_WORKFLOW_REPORT_FILE

    def __post_init__(self) -> None:
        os.environ["MODEL_API_KEY"] = self.model_api_key

    @property
    def workflow_log_path(self) -> Path:
        return _resolve_project_path(self.workflow_log_file)

    @property
    def workflow_report_path(self) -> Path:
        return _resolve_project_path(self.workflow_report_file)

    def get_model_name(self, strength: ModelStrength) -> str:
        return {
            ModelStrength.LOW: "google/gemini-2.5-flash-lite",
            ModelStrength.MEDIUM: "google/gemini-2.5-flash",
            ModelStrength.HIGH: "google/gemini-2.5-pro",
        }[strength]


def _load_dotenv_if_available() -> None:
    if load_dotenv is None:
        return
    load_dotenv()


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    _load_dotenv_if_available()

    model_api_key = os.environ.get("MODEL_API_KEY")
    if not model_api_key:
        raise RuntimeError(
            "MODEL_API_KEY is required. Set it in your environment or .env file."
        )

    model_name = os.environ.get("GENAI_MODEL_NAME", DEFAULT_MODEL_NAME)
    model_provider = os.environ.get("GENAI_MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER)

    workflow_log_file = os.environ.get("WORKFLOW_LOG_FILE", DEFAULT_WORKFLOW_LOG_FILE)
    workflow_report_file = os.environ.get(
        "WORKFLOW_REPORT_FILE", DEFAULT_WORKFLOW_REPORT_FILE
    )

    return Settings(
        model_api_key=model_api_key,
        model_name=model_name,
        model_provider=model_provider,
        workflow_log_file=workflow_log_file,
        workflow_report_file=workflow_report_file,
    )
