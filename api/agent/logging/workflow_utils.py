from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token, copy_context
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import threading
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar
from uuid import UUID, uuid4

import config as config

_CURRENT_STEP_UUID: ContextVar[str | None] = ContextVar(
    "workflow_step_uuid", default=None
)
_LOG_LOCK = threading.Lock()
P = ParamSpec("P")
R = TypeVar("R")


def generate_step_uuid() -> str:
    return str(uuid4())


def enter_step(step_uuid: str) -> tuple[str | None, Token]:
    caller_uuid = _CURRENT_STEP_UUID.get()
    token = _CURRENT_STEP_UUID.set(step_uuid)
    return caller_uuid, token


def exit_step(token: Token) -> None:
    _CURRENT_STEP_UUID.reset(token)


def bind_logger_to_current_step_context(
    func: Callable[P, R],
) -> Callable[P, R]:
    context = copy_context()

    def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return context.run(func, *args, **kwargs)

    return _wrapper


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        enum_value = value.value
        if isinstance(enum_value, (bool, int, float, str)):
            return enum_value
        return value.name
    if isinstance(value, (UUID, Path)):
        return str(value)
    if is_dataclass(value):
        return {
            field.name: _serialize_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialize_value(item) for item in value]
    return repr(value)


def log_step(
    step_uuid: str,
    caller_uuid: str | None,
    step_class: str,
    step_module: str,
    input_value: Any,
    output_value: Any,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step_uuid": step_uuid,
        "caller_uuid": caller_uuid,
        "step_class": step_class,
        "step_module": step_module,
        "input": _serialize_value(input_value),
        "output": _serialize_value(output_value),
    }
    print("Logging step:", step_module, step_class, step_uuid)
    path = Path(config.load_settings().workflow_log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")


__all__ = [
    "bind_logger_to_current_step_context",
    "enter_step",
    "exit_step",
    "generate_step_uuid",
    "log_step",
]
