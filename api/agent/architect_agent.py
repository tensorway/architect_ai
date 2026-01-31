from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agent.logging.checkpoints import log_checkpoint
from agent.svg_catalog import (
    SvgAssetDefinition,
    load_svg_catalog,
    normalize_name,
    parse_number,
    scale_for_width,
)
from agent.workflow_steps.furniture_layout_step import (
    FurnitureLayoutStep,
    FurniturePlannerInput,
)
from agent.workflow_steps.floor_planner_step import FloorPlannerStep
from agent.workflow_steps.planner_types import PlannerDraftOutput
from agent.workflow_steps.workflow import WorkflowStep


@dataclass
class ArchitectAgentInput:
    prompt: str


@dataclass
class ArchitectAgentOutput:
    plan: Mapping[str, Any]
    view: Mapping[str, Any] | None = None
    prompt: str = ""
    notes: str = ""


class ArchitectAgent(WorkflowStep[ArchitectAgentInput, ArchitectAgentOutput]):
    assets_dir = Path(__file__).resolve().parents[1] / "models"

    def __init__(self) -> None:
        self._catalog = load_svg_catalog(self.assets_dir)
        asset_names = [asset.name for asset in self._catalog.values()]
        self._floor_planner = FloorPlannerStep(asset_names=asset_names)
        self._furnisher = FurnitureLayoutStep(asset_names=asset_names)
        super().__init__()

    def _run(self, input: ArchitectAgentInput) -> ArchitectAgentOutput:
        log_checkpoint("Drafting bare floor plan…")
        floor_draft: PlannerDraftOutput = self._floor_planner.run(input)

        log_checkpoint("Placing furniture symbols…")
        furniture_draft: PlannerDraftOutput = self._furnisher.run(
            FurniturePlannerInput(
                prompt=input.prompt, walls=floor_draft.plan.get("walls") or []
            )
        )

        resolved_plan, resolve_notes = self._resolve_assets(
            {
                "walls": floor_draft.plan.get("walls") or [],
                "assets": furniture_draft.plan.get("assets") or [],
            }
        )

        combined_notes = "; ".join(
            note
            for note in [
                floor_draft.notes.strip(),
                furniture_draft.notes.strip(),
                resolve_notes.strip(),
            ]
            if note
        )

        return ArchitectAgentOutput(
            plan=resolved_plan,
            view=furniture_draft.view or floor_draft.view,
            prompt=furniture_draft.prompt or floor_draft.prompt,
            notes=combined_notes,
        )

    def _resolve_assets(
        self, plan_payload: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], str]:
        walls = plan_payload.get("walls") or []
        raw_assets = plan_payload.get("assets") or []

        resolved_assets = []
        missing_assets: list[str] = []

        for idx, raw in enumerate(raw_assets):
            if not isinstance(raw, Mapping):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue

            asset_def = self._catalog.get(normalize_name(name))
            if not asset_def:
                missing_assets.append(name)
                continue

            resolved_assets.append(self._materialize_asset(asset_def, raw, idx))

        notes = (
            f"Skipped unknown assets: {', '.join(sorted(set(missing_assets)))}"
            if missing_assets
            else ""
        )

        plan = {**plan_payload, "walls": walls, "assets": resolved_assets}
        return plan, notes

    def _materialize_asset(
        self, asset_def: SvgAssetDefinition, raw: Mapping[str, Any], idx: int
    ) -> Mapping[str, Any]:
        asset_id = str(raw.get("id") or f"a{idx + 1}")
        x = parse_number(raw.get("x"), 0.0) or 0.0
        y = parse_number(raw.get("y"), 0.0) or 0.0
        rotation = parse_number(raw.get("rotationDeg"), 0.0) or 0.0

        width_m = parse_number(raw.get("widthM"))
        scale = parse_number(raw.get("scale"))
        if scale is None or scale <= 0:
            target_width_m = width_m if width_m and width_m > 0 else 1.0
            scale = scale_for_width(asset_def.vbW, target_width_m)

        return {
            "id": asset_id,
            "name": asset_def.name,
            "inner": asset_def.inner,
            "vbW": asset_def.vbW,
            "vbH": asset_def.vbH,
            "x": x,
            "y": y,
            "scale": scale,
            "rotationDeg": rotation,
        }


def build_architect_agent() -> ArchitectAgent:
    return ArchitectAgent()


__all__ = [
    "ArchitectAgent",
    "ArchitectAgentInput",
    "ArchitectAgentOutput",
    "build_architect_agent",
]
