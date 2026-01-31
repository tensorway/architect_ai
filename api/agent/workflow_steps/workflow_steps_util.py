from __future__ import annotations

import json
import re
from typing import Any, Dict

__all__ = ["strip_code_fence", "extract_json_payload"]


_CODE_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def strip_code_fence(text: str) -> str:
    if "```" not in text:
        return text

    match = _CODE_FENCE_PATTERN.search(text)
    if match:
        return match.group(1)
    return text


def extract_json_payload(
    text: str,
    *,
    coerce_values_to_str: bool = False,
) -> Dict[str, Any]:
    if not text:
        return {}

    candidate = strip_code_fence(text.strip())

    brace_start = candidate.find("{")
    brace_end = candidate.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_start < brace_end:
        candidate = candidate[brace_start : brace_end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    if coerce_values_to_str:
        return {str(key): str(value) for key, value in parsed.items()}

    return dict(parsed)
