from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from langchain_core.prompts import ChatPromptTemplate

from agent.logging.checkpoints import log_checkpoint
from agent.workflow_steps.workflow_llm_step import WorkflowLlmStep
from config import ModelStrength


@dataclass
class ArchitectAgentInput:
    prompt: str


@dataclass
class ArchitectAgentOutput:
    plan: Mapping[str, Any]
    view: Mapping[str, Any] | None = None
    prompt: str = ""
    notes: str = ""


class ArchitectAgent(WorkflowLlmStep[ArchitectAgentInput, ArchitectAgentOutput]):
    output_type = ArchitectAgentOutput
    model_strength = ModelStrength.MEDIUM

    def _build_prompt(self) -> ChatPromptTemplate:
        tv_svg_inner = (
            r'<g xmlns="http://www.w3.org/2000/svg" transform="translate(-16.044039,-83.803322)">'
            r"<g>"
            r'<rect style="fill:none;stroke:#000000;stroke-width:0.75" width="61.756626" height="3.2600846" x="19.430269" y="84.178322"/>'
            r'<rect style="fill:none;stroke:#000000;stroke-width:0.75" width="67.779091" height="2.6012869" x="16.419039" y="87.438408"/>'
            r"</g>"
            r"</g>"
        )
        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert residential architect and space planner. "
                    "Return ONLY valid JSON; no code fences or prose. "
                    "Schema: {{\n"
                    '  "plan": {{\n'
                    '    "walls": [ {{ "id": string, "a": {{"x": number, "y": number}}, "b": {{"x": number, "y": number}} }} ],\n'
                    '    "assets": [ {{ "id": string, "name": string, "inner": string, "vbW": number, "vbH": number, "x": number, "y": number, "scale": number, "rotationDeg": number }} ]\n'
                    "  }},\n"
                    '  "view": {{ "x": number, "y": number, "scale": number }},\n'
                    '  "prompt": string,\n'
                    '  "notes": string\n'
                    "}}. "
                    "Coordinates are in SVG pixels within a 1200x800 viewbox; keep layouts centered and scaled realistically. "
                    "Walls should form a plausible floorplan matching the brief. "
                    "If you include a TV asset, use the provided inner SVG exactly: "
                    f"{tv_svg_inner} with vbW=68.529092 and vbH=6.6113729. "
                    "Use concise ids like w1, w2, a1. "
                    "If unsure, still produce a simple rectangular layout. "
                    "Do not invent custom SVG; zero or a few TVs are fine."
                ),
                (
                    "human",
                    "Design brief: {prompt}\n"
                    "Return JSON now."
                ),
            ]
        )

    def _run(self, input: ArchitectAgentInput) -> ArchitectAgentOutput:
        log_checkpoint("Drafting layout options…")
        return super()._run(input)


def build_architect_agent() -> ArchitectAgent:
    return ArchitectAgent()


__all__ = [
    "ArchitectAgent",
    "ArchitectAgentInput",
    "ArchitectAgentOutput",
    "build_architect_agent",
]
