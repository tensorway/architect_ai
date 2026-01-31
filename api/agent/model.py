"""Utilities for initialising LangChain chat models."""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from config import ModelStrength, load_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_chat_model(strength: ModelStrength) -> BaseChatModel:
    settings = load_settings()

    return init_chat_model(
        settings.get_model_name(strength),
        model_provider=settings.model_provider,
        api_key=settings.model_api_key,
        base_url=OPENROUTER_BASE_URL,
    )
