"""Lightweight checkpoint logging helpers used to surface progress updates."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Callable, Optional

CheckpointCallback = Callable[[str], None]

_CHECKPOINT_CALLBACK: ContextVar[Optional[CheckpointCallback]] = ContextVar(
    "checkpoint_callback", default=None
)


def set_checkpoint_callback(callback: Optional[CheckpointCallback]) -> Token:
    """Register a callback for the current context and return its token."""
    return _CHECKPOINT_CALLBACK.set(callback)


def reset_checkpoint_callback(token: Token) -> None:
    """Reset the checkpoint callback to the previous value."""
    _CHECKPOINT_CALLBACK.reset(token)


def log_checkpoint(message: str) -> None:
    """Emit a checkpoint message and notify the registered callback."""
    text = (message or "").strip()
    if not text:
        return

    logging.info("Checkpoint: %s", text)
    callback = _CHECKPOINT_CALLBACK.get()
    if not callback:
        return

    try:
        callback(text)
    except Exception:  # pragma: no cover - defensive logging
        logging.exception("Checkpoint callback failed.")


__all__ = ["log_checkpoint", "reset_checkpoint_callback", "set_checkpoint_callback"]
