from __future__ import annotations

from typing import Any, Sequence

from langchain_core.prompts import ChatPromptTemplate

from agent.workflow_steps.planner_types import PlannerDraftOutput
from agent.workflow_steps.workflow_llm_step import WorkflowLlmStep
from config import ModelStrength


class FloorPlannerStep(WorkflowLlmStep[Any, PlannerDraftOutput]):
    """
    Generates the architectural shell only (walls). No windows, doors, or furniture.
    """

    output_type = PlannerDraftOutput
    model_strength = ModelStrength.MEDIUM

    def __init__(self, *, asset_names: Sequence[str]):
        # asset_names kept for compatibility; not used in the prompt but useful for parity.
        self.asset_names = tuple(asset_names)
        super().__init__()

    def _build_prompt(self) -> ChatPromptTemplate:
        schema_block = (
            "{{\\n"
            '  "plan": {{\\n'
            '    "walls": [ {{ "id": string, "a": {{"x": number, "y": number}}, "b": {{"x": number, "y": number}} }} ],\\n'
            '    "assets": []\\n'
            "  }},\\n"
            '  "view"?: {{ "x": number, "y": number, "scale": number }},\\n'
            '  "prompt": string,\\n'
            '  "notes": string\\n'
            "}}"
        )

        rules_block = (
            "Rules:\\n"
            "- Coordinates use a 1200x800 SVG viewBox (pixels). Keep the layout centered.\\n"
            "- Use short ids like w1; ids may be auto-filled if omitted.\\n"
            "- Focus ONLY on the floorplan shell: straight walls that form a plausible layout matching the brief.\\n"
            "- assets must be an empty array [].\\n"
            "- Do NOT include SVG XML; it will be filled automatically."
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


__all__ = ["FloorPlannerStep"]
