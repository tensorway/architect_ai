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
from agent.workflow_steps.room_requirements_step import (
    RoomRequirementsInput,
    RoomRequirementsOutput,
    RoomRequirementsStep,
)
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
        self._room_requirements = RoomRequirementsStep()
        super().__init__()

    def _run(self, input: ArchitectAgentInput) -> ArchitectAgentOutput:
        floor_draft = self._draft_floor(input)
        rooms = floor_draft.plan.get("rooms") or []

        room_requirements = self._extract_room_requirements(input.prompt, rooms)
        assets, furn_view, furn_prompt, furn_notes = self._layout_furniture(
            input.prompt, floor_draft, rooms, room_requirements
        )

        resolved_plan, resolve_notes = self._resolve_assets(
            {
                "walls": floor_draft.plan.get("walls") or [],
                "rooms": rooms,
                "assets": assets,
                "roomRequirements": [req.__dict__ for req in room_requirements],
            }
        )

        combined_notes = "; ".join(
            note
            for note in [
                floor_draft.notes.strip(),
                furn_notes,
                resolve_notes.strip(),
                "; ".join(
                    req.notes.strip() for req in room_requirements if req.notes.strip()
                ),
            ]
            if note
        )

        return ArchitectAgentOutput(
            plan=resolved_plan,
            view=furn_view or floor_draft.view,
            prompt=furn_prompt or floor_draft.prompt,
            notes=combined_notes,
        )

    def _draft_floor(self, input: ArchitectAgentInput) -> PlannerDraftOutput:
        log_checkpoint("Drafting bare floor plan…")
        return self._floor_planner.run(input)

    def _extract_room_requirements(
        self, prompt: str, rooms: list[Mapping[str, Any]]
    ) -> list[RoomRequirementsOutput]:
        if not rooms:
            return []
        log_checkpoint("Extracting room-level requirements…")
        requirements: list[RoomRequirementsOutput] = []
        for room in rooms:
            room_id = str(room.get("id") or "").strip()
            if not room_id:
                continue
            req = self._room_requirements.run(
                RoomRequirementsInput(
                    prompt=prompt,
                    room_id=room_id,
                    room_label=str(room.get("label") or ""),
                    room_description=str(room.get("description") or ""),
                )
            )
            requirements.append(req)
        return requirements

    def _layout_furniture(
        self,
        user_prompt: str,
        floor_draft: PlannerDraftOutput,
        rooms: list[Mapping[str, Any]],
        room_requirements: list[RoomRequirementsOutput],
    ) -> tuple[list[Mapping[str, Any]], Mapping[str, Any] | None, str, str]:
        if not rooms:
            return [], None, "", ""
        if not room_requirements:
            return self._layout_single_pass(user_prompt, floor_draft)
        return self._layout_room_by_room(user_prompt, floor_draft, rooms, room_requirements)

    def _layout_single_pass(
        self, user_prompt: str, floor_draft: PlannerDraftOutput
    ) -> tuple[list[Mapping[str, Any]], Mapping[str, Any] | None, str, str]:
        log_checkpoint("Placing furniture (single pass)…")
        draft = self._furnisher.run(
            FurniturePlannerInput(
                prompt=user_prompt, walls=floor_draft.plan.get("walls") or []
            )
        )
        return (
            draft.plan.get("assets") or [],
            draft.view,
            draft.prompt or "",
            draft.notes.strip(),
        )

    def _layout_room_by_room(
        self,
        user_prompt: str,
        floor_draft: PlannerDraftOutput,
        rooms: list[Mapping[str, Any]],
        room_requirements: list[RoomRequirementsOutput],
    ) -> tuple[list[Mapping[str, Any]], Mapping[str, Any] | None, str, str]:
        log_checkpoint("Placing furniture room-by-room…")
        wall_lookup = self._build_wall_lookup(floor_draft.plan.get("walls") or [])
        req_by_room = {req.room_id: req for req in room_requirements}

        assets: list[Mapping[str, Any]] = []
        notes: list[str] = []
        prompts: list[str] = []
        view = None

        for room in rooms:
            room_id = str(room.get("id") or "").strip()
            if not room_id:
                continue
            req = req_by_room.get(room_id)
            walls = self._walls_for_room(room, wall_lookup, floor_draft)
            room_prompt = self._build_room_prompt(user_prompt, room, req)
            draft = self._furnisher.run(
                FurniturePlannerInput(prompt=room_prompt, walls=walls)
            )
            assets.extend(draft.plan.get("assets") or [])
            if draft.notes:
                notes.append(draft.notes.strip())
            if draft.prompt:
                prompts.append(draft.prompt.strip())
            if not view and draft.view:
                view = draft.view

        return assets, view, "; ".join(prompts), "; ".join(notes)

    def _build_wall_lookup(
        self, walls: list[Mapping[str, Any]]
    ) -> dict[str, Mapping[str, Any]]:
        return {
            str(w.get("id")): w for w in walls if isinstance(w, Mapping) and w.get("id")
        }

    def _walls_for_room(
        self,
        room: Mapping[str, Any],
        wall_lookup: Mapping[str, Mapping[str, Any]],
        floor_draft: PlannerDraftOutput,
    ) -> list[Mapping[str, Any]]:
        wall_ids = room.get("wallIds") or []
        room_walls = [wall_lookup[wid] for wid in wall_ids if wid in wall_lookup]
        return room_walls or list(floor_draft.plan.get("walls") or [])

    def _build_room_prompt(
        self,
        user_prompt: str,
        room: Mapping[str, Any],
        req: RoomRequirementsOutput | None,
    ) -> str:
        parts = [user_prompt]
        room_label = str(room.get("label") or (req.label if req else "") or "").strip()
        room_desc = str(room.get("description") or "").strip()
        focus = f"Room focus: {room_label or room.get('id')}"
        if room_desc:
            focus += f" — {room_desc}"
        parts.append(focus)

        if req:
            parts.append(f"Requested furniture: {self._summarize(req.furniture)}")
            parts.append(f"Requested windows: {self._summarize(req.windows)}")
            parts.append(f"Requested doors: {self._summarize(req.doors)}")

        return "\n".join(parts)

    def _summarize(self, items: list[Mapping[str, Any]]) -> str:
        if not items:
            return "none specified"
        return "; ".join(
            f"{item.get('quantity', '')} {item.get('name', '')} {item.get('details', '')}".strip()
            for item in items
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
