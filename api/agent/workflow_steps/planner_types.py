from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class PlannerDraftOutput:
    plan: Mapping[str, Any]
    view: Mapping[str, Any] | None = None
    prompt: str = ""
    notes: str = ""


__all__ = ["PlannerDraftOutput"]
