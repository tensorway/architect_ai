from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from langchain_core.prompts import ChatPromptTemplate

from agent.workflow_steps.workflow_llm_step import WorkflowLlmStep
from config import ModelStrength


@dataclass
class RoomRequirementsInput:
    """Inputs needed to scope extraction to a single room."""

    prompt: str
    room_id: str
    room_label: str
    room_description: str


@dataclass
class RoomRequirementsOutput:
    """What the user requested for a specific room."""

    room_id: str
    label: str
    description: str
    furniture: list[Mapping[str, Any]] = field(default_factory=list)
    windows: list[Mapping[str, Any]] = field(default_factory=list)
    doors: list[Mapping[str, Any]] = field(default_factory=list)
    notes: str = ""


class RoomRequirementsStep(
    WorkflowLlmStep[RoomRequirementsInput, RoomRequirementsOutput]
):
    """
    Extracts the room-specific items (furniture, windows, doors) the user asked for.
    """

    output_type = RoomRequirementsOutput
    model_strength = ModelStrength.LOW

    def _build_prompt(self) -> ChatPromptTemplate:
        schema_block = (
            "{{\\n"
            '  "room_id": string,\\n'
            '  "label": string,\\n'
            '  "description": string,\\n'
            '  "furniture": [ {{ "name": string, "quantity"?: integer, "details"?: string }} ],\\n'
            '  "windows": [ {{ "name": string, "quantity"?: integer, "details"?: string }} ],\\n'
            '  "doors": [ {{ "name": string, "quantity"?: integer, "details"?: string }} ],\\n'
            '  "notes": string\\n'
            "}}"
        )

        rules_block = (
            "Rules:\\n"
            "- Consider only items the user explicitly requests for this room; leave arrays empty if none.\\n"
            "- Keep wording close to the user's ask (style, size, material).\\n"
            "- Do NOT invent quantities; include quantity only when the prompt states or implies a count.\\n"
            "- Use details to capture placement or adjacency hints (e.g., 'along north wall', 'next to window').\\n"
            "- Global wishes apply only if they naturally belong to this room; otherwise omit.\\n"
            "- Return ONLY valid JSON; no code fences, no extra commentary."
        )

        system_prompt = (
            "You are an assistant extracting room-level furnishing requirements. "
            f"Return ONLY valid JSON. Schema: {schema_block} {rules_block}"
        )

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "User design brief (verbatim): {prompt}\n"
                    "Target room id: {room_id}\n"
                    "Room label: {room_label}\n"
                    "Room description: {room_description}\n"
                    "Extract only what belongs in this room. Return JSON now.",
                ),
            ]
        )


__all__ = [
    "RoomRequirementsInput",
    "RoomRequirementsOutput",
    "RoomRequirementsStep",
]
