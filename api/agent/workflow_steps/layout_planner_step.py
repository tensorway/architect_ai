from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from langchain_core.prompts import ChatPromptTemplate

from agent.workflow_steps.workflow_llm_step import WorkflowLlmStep
from config import ModelStrength


@dataclass
class PlannerDraftOutput:
    plan: Mapping[str, Any]
    view: Mapping[str, Any] | None = None
    prompt: str = ""
    notes: str = ""


class LayoutPlannerStep(WorkflowLlmStep[Any, PlannerDraftOutput]):
    output_type = PlannerDraftOutput
    model_strength = ModelStrength.MEDIUM

    def __init__(self, *, asset_names: Sequence[str]):
        self.asset_names = tuple(asset_names)
        super().__init__()

    def _build_prompt(self) -> ChatPromptTemplate:
        assets_text = "\n".join(f"- {name}" for name in self.asset_names)
        schema_block = (
            "{{\\n"
            '  "plan": {{\\n'
            '    "walls": [ {{ "id": string, "a": {{"x": number, "y": number}}, "b": {{"x": number, "y": number}} }} ],\\n'
            '    "assets": [ {{ "id"?: string, "name": string, "x": number, "y": number, "rotationDeg"?: number, "widthM"?: number, "scale"?: number }} ]\\n'
            "  }},\\n"
            '  "view"?: {{ "x": number, "y": number, "scale": number }},\\n'
            '  "prompt": string,\\n'
            '  "notes": string\\n'
            "}}"
        )

        rules_block = (
            "Rules:\\n"
            "- Coordinates use a 1200x800 SVG viewBox (pixels). Keep the layout centered.\\n"
            "- Use short ids like w1, a1; ids may be auto-filled if omitted.\\n"
            "- Choose assets ONLY from this library (names verbatim):\\n"
            f"{assets_text}\\n"
            "- Do NOT include SVG XML; it will be filled automatically.\\n"
            "- Provide a realistic widthM (meters) for each asset; set rotationDeg when needed.\\n"
            "- Walls should form a plausible floorplan that matches the brief."
        )

        system_prompt = (
            "You are an expert residential architect and space planner. "
            f"Return ONLY valid JSON (no code fences). Schema: {schema_block}. "
            f"{rules_block}"
        )

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "Design brief: {prompt}\n"
                    "Return JSON now."
                ),
            ]
        )
