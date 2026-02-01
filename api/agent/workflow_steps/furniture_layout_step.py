from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from langchain_core.prompts import ChatPromptTemplate

from agent.workflow_steps.planner_types import PlannerDraftOutput
from agent.workflow_steps.workflow_llm_step import WorkflowLlmStep
from config import ModelStrength


@dataclass
class FurniturePlannerInput:
    prompt: str
    walls: Sequence[Mapping[str, Any]]


class FurnitureLayoutStep(WorkflowLlmStep[FurniturePlannerInput, PlannerDraftOutput]):
    """
    Places furniture assets onto a provided immutable wall layout.
    """

    output_type = PlannerDraftOutput
    model_strength = ModelStrength.MEDIUM

    def __init__(self, *, asset_names: Sequence[str]):
        self.asset_names = tuple(asset_names)
        super().__init__()

    def _build_prompt_inputs(self, input: FurniturePlannerInput) -> Mapping[str, object]:
        data = super()._build_prompt_inputs(input)
        data["walls_json"] = json.dumps(input.walls, separators=(",", ":"))
        return data

    def _build_prompt(self) -> ChatPromptTemplate:
        assets_text = "\n".join(f"- {name}" for name in self.asset_names)
        schema_block = (
            "{{\\n"
            '  "walls": [ {{ "id": string, "a": {{"x": number, "y": number}}, "b": {{"x": number, "y": number}} }} ],\\n'
            '  "rooms": [],\\n'
            '  "assets": [ {{ "id"?: string, "name": string, "x": number, "y": number }} ],\\n'
            '  "roomRequirements": [],\\n'
            '  "view"?: {{ "x": number, "y": number, "scale": number }},\\n'
            '  "prompt": string,\\n'
            '  "notes": string\\n'
            "}}"
        )

        rules_block = (
            "Rules:\\n"
            "- Use the provided walls exactly; do NOT move, delete, or add walls.\\n"
            "- Populate ONLY the assets array with furniture; no doors or windows.\\n"
            "- Coordinates use a 1200x800 SVG viewBox (pixels). Keep placements aligned with the rooms.\\n"
            "- Choose assets ONLY from this library (names verbatim):\\n"
            f"{assets_text}\\n"
            "- Do NOT include SVG XML; it will be filled automatically.\\n"
            "- roomRequirements must be an empty array []."
        )

        system_prompt = (
            "You are an interior designer placing furniture on an existing floorplan. "
            f"Return ONLY valid JSON (no code fences). Schema: {schema_block}. "
            f"{rules_block}"
        )

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "Design brief: {prompt}\n"
                    "Existing walls (immutable): {walls_json}\n"
                    "Return JSON now."
                ),
            ]
        )


__all__ = ["FurnitureLayoutStep", "FurniturePlannerInput"]
