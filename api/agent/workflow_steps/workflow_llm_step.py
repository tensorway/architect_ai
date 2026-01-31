from __future__ import annotations

from dataclasses import MISSING, Field, fields
import logging
from typing import (
    Any,
    Generic,
    Iterable,
    Iterator,
    Mapping,
    TypeVar,
    get_args,
    get_origin,
)

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from config import ModelStrength
from agent.model import build_chat_model

from agent.workflow_steps.workflow import WorkflowStep
from agent.workflow_steps.workflow_steps_util import extract_json_payload
from collections.abc import Sequence

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")

logger = logging.getLogger(__name__)


class WorkflowLlmStep(WorkflowStep[InputT, OutputT], Generic[InputT, OutputT]):
    output_type: type[OutputT]
    model_strength: ModelStrength = ModelStrength.LOW

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.prompt = self._build_prompt()
        super().__init__(*args, **kwargs)

    def _run(self, input: InputT) -> OutputT:
        model = self._extract_model(input)
        messages = list(self._build_messages(input))
        response = model.invoke(messages)
        content = self._extract_content(response)
        json_output = extract_json_payload(content if isinstance(content, str) else "")
        return self._instantiate_output(json_output)

    def stream(self, input: InputT) -> Iterator[str]:
        model = self._extract_model(input)
        for chunk in model.stream(self._build_messages(input)):
            content = self._extract_content(chunk)
            if content:
                yield content

    def _build_messages(self, input: InputT) -> Iterable[BaseMessage]:
        prompt_inputs = self._build_prompt_inputs(input)
        prompt_value = self.prompt.invoke(prompt_inputs)
        return prompt_value.to_messages()

    def _build_prompt_inputs(self, input: InputT) -> Mapping[str, object]:
        data = self._input_to_mapping(input)
        for key, value in data.items():
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                data[key] = "\n".join(f"- {item}" for item in value)
        return data

    def _build_prompt(self) -> ChatPromptTemplate:
        raise NotImplementedError

    def _extract_model(self, input: InputT) -> BaseChatModel:
        return build_chat_model(self.model_strength)

    def _extract_content(self, response: object) -> str:
        return getattr(response, "content", response) or ""

    def _instantiate_output(self, payload: Mapping[str, Any]) -> OutputT:
        output_cls = self.output_type
        field_defs: Mapping[str, Field[Any]] = {
            field.name: field for field in fields(output_cls)
        }
        kwargs: dict[str, Any] = {}
        for name, field_def in field_defs.items():
            if name not in payload:
                continue
            raw_value = payload[name]
            coerced = self._coerce_field_value(field_def.type, raw_value)
            kwargs[name] = coerced
        filled_kwargs = self._fill_missing_output_fields(output_cls, field_defs, kwargs)
        return output_cls(**filled_kwargs)

    def _fill_missing_output_fields(
        self,
        output_cls: type[OutputT],
        field_defs: Mapping[str, Field[Any]],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        completed = dict(kwargs)
        missing_fields: list[str] = []
        for name, field_def in field_defs.items():
            if name in completed:
                continue
            completed[name] = self._default_output_value(field_def)
            missing_fields.append(name)
        if missing_fields:
            logger.warning(
                "LLM output for %s missing fields: %s. Using default values.",
                output_cls.__name__,
                ", ".join(sorted(missing_fields)),
            )
        return completed

    def _default_output_value(self, field_def: Field[Any]) -> Any:
        if field_def.default is not MISSING:
            return field_def.default
        default_factory = getattr(field_def, "default_factory", MISSING)
        if default_factory is not MISSING:
            return default_factory()
        return self._default_for_annotation(field_def.type)

    def _default_for_annotation(self, annotation: Any) -> Any:
        target = self._unwrap_optional(annotation)
        if target is bool:
            return False
        if target in (int, float):
            return target()
        if target is str:
            return ""
        return None

    def _coerce_field_value(self, annotation: Any, value: Any) -> Any:
        target = self._unwrap_optional(annotation)
        if target is bool:
            return self._coerce_bool(value)
        if target is str:
            return "" if value is None else str(value)
        return value

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().casefold()
            if lowered in {
                "true",
                "yes",
                "y",
                "1",
                "approved",
                "approve",
                "valid",
                "relevant",
                "correct",
            }:
                return True
            if lowered in {
                "false",
                "no",
                "n",
                "0",
                "reject",
                "rejected",
                "invalid",
                "incorrect",
            }:
                return False
        return bool(value)

    def _unwrap_optional(self, annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin is None:
            return annotation
        args = get_args(annotation)
        if not args:
            return annotation
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and len(non_none) != len(args):
            return non_none[0]
        return annotation

    def _input_to_mapping(self, input: InputT) -> dict[str, Any]:
        return {field.name: getattr(input, field.name) for field in fields(input)}

    def _describe_annotation(self, annotation: Any) -> str:
        if isinstance(annotation, str):
            return annotation
        origin = get_origin(annotation)
        if isinstance(annotation, type):
            return annotation.__name__
        if origin is not None:
            args = get_args(annotation)
            arg_text = ", ".join(self._describe_annotation(arg) for arg in args)
            origin_name = getattr(origin, "__name__", str(origin))
            return f"{origin_name}[{arg_text}]" if arg_text else origin_name
        return str(annotation)

    def build_output_format(self) -> str:
        fields = ", ".join(
            f"`{field.name}` ({self._describe_annotation(field.type)})"
            for field in self.output_type.__dataclass_fields__.values()
        )
        return f"Respond ONLY with JSON containing the following keys: {fields}."
