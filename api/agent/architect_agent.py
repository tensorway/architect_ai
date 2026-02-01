from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.logging.checkpoints import log_checkpoint
from agent.svg_catalog import (
    SvgAssetDefinition,
    load_svg_catalog,
    normalize_name,
    parse_number,
)
from agent.workflow_steps.furniture_layout_step import (
    FurnitureLayoutStep,
    FurniturePlannerInput,
)
from agent.workflow_steps.floor_planner_step import FloorPlannerStep
from agent.workflow_steps.planner_types import (
    Asset,
    RequestedItem,
    PlannerDraftOutput,
    Room,
    RoomRequirement,
    Viewport,
    Wall,
)
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
    walls: list[Wall]
    rooms: list[Room]
    assets: list[Asset]
    roomRequirements: list[RoomRequirement]
    view: Viewport | None = None
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
        walls = floor_draft.walls or []
        rooms = floor_draft.rooms or []

        room_requirements = self._extract_room_requirements(input.prompt, rooms)
        assets, furn_view, furn_prompt, furn_notes = self._layout_furniture(
            input.prompt, floor_draft, rooms, room_requirements
        )

        room_requirement_descriptions = [
            req.description for req in room_requirements if req.description
        ]

        resolved_assets, resolve_notes = self._resolve_assets(assets)

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
            walls=walls,
            rooms=rooms,
            assets=resolved_assets,
            roomRequirements=room_requirement_descriptions,
            view=furn_view or floor_draft.view,
            prompt=furn_prompt or floor_draft.prompt,
            notes=combined_notes,
        )

    def _draft_floor(self, input: ArchitectAgentInput) -> PlannerDraftOutput:
        log_checkpoint("Drafting bare floor plan…")
        return self._floor_planner.run(input)

    def _extract_room_requirements(
        self, prompt: str, rooms: list[Room]
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
        rooms: list[Room],
        room_requirements: list[RoomRequirementsOutput],
    ) -> tuple[list[Asset], Viewport | None, str, str]:
        if not rooms:
            return [], None, "", ""
        if not room_requirements:
            return self._layout_single_pass(user_prompt, floor_draft)
        return self._layout_room_by_room(user_prompt, floor_draft, rooms, room_requirements)

    def _layout_single_pass(
        self, user_prompt: str, floor_draft: PlannerDraftOutput
    ) -> tuple[list[Asset], Viewport | None, str, str]:
        log_checkpoint("Placing furniture (single pass)…")
        draft = self._furnisher.run(
            FurniturePlannerInput(
                prompt=user_prompt, walls=floor_draft.walls or []
            )
        )
        return (
            draft.assets or [],
            draft.view,
            draft.prompt or "",
            draft.notes.strip(),
        )

    def _layout_room_by_room(
        self,
        user_prompt: str,
        floor_draft: PlannerDraftOutput,
        rooms: list[Room],
        room_requirements: list[RoomRequirementsOutput],
    ) -> tuple[list[Asset], Viewport | None, str, str]:
        log_checkpoint("Placing furniture room-by-room…")
        wall_lookup = self._build_wall_lookup(floor_draft.walls or [])
        req_by_room = {req.room_id: req for req in room_requirements}

        assets: list[Asset] = []
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
            assets.extend(draft.assets or [])
            if draft.notes:
                notes.append(draft.notes.strip())
            if draft.prompt:
                prompts.append(draft.prompt.strip())
            if not view and draft.view:
                view = draft.view

        return assets, view, "; ".join(prompts), "; ".join(notes)

    def _build_wall_lookup(self, walls: list[Wall] | None) -> dict[str, Wall]:
        if not walls:
            return {}
        return {w["id"]: w for w in walls if w.get("id")}

    def _walls_for_room(
        self,
        room: Room,
        wall_lookup: dict[str, Wall],
        floor_draft: PlannerDraftOutput,
    ) -> list[Wall]:
        wall_ids = room.get("wallIds") or []
        room_walls = [wall_lookup[wid] for wid in wall_ids if wid in wall_lookup]
        return room_walls or list(floor_draft.walls or [])

    def _build_room_prompt(
        self,
        user_prompt: str,
        room: Room,
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

    def _summarize(self, items: list[RequestedItem]) -> str:
        if not items:
            return "none specified"
        return "; ".join(
            f"{item.get('quantity', '')} {item.get('name', '')} {item.get('details', '')}".strip()
            for item in items
        )

    def _resolve_assets(self, raw_assets: list[Asset]) -> tuple[list[Asset], str]:
        resolved_assets: list[Asset] = []
        missing_assets: list[str] = []

        for idx, raw in enumerate(raw_assets):
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

        return resolved_assets, notes

    def _materialize_asset(
        self, asset_def: SvgAssetDefinition, raw: Asset, idx: int
    ) -> Asset:
        asset_id = str(raw.get("id") or f"a{idx + 1}")
        x = parse_number(raw.get("x"), 0.0) or 0.0
        y = parse_number(raw.get("y"), 0.0) or 0.0
        return {
            "id": asset_id,
            "name": asset_def.name,
            "inner": asset_def.inner,
            "vbW": asset_def.vbW,
            "vbH": asset_def.vbH,
            "scale": parse_number(raw.get("scale"), 1.0) or 1.0,
            "rotationDeg": parse_number(raw.get("rotationDeg"), 0.0) or 0.0,
            "x": x,
            "y": y,
        }


def build_architect_agent() -> ArchitectAgent:
    return ArchitectAgent()


__all__ = [
    "ArchitectAgent",
    "ArchitectAgentInput",
    "ArchitectAgentOutput",
    "build_architect_agent",
]
