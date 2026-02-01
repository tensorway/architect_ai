from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class Point(TypedDict):
    x: float
    y: float


class Wall(TypedDict):
    id: str
    a: Point
    b: Point


class Room(TypedDict, total=False):
    id: str
    wallIds: list[str]
    label: str
    description: str
    vertices: list[Point]
    area: float


class Asset(TypedDict, total=False):
    name: str
    x: float
    y: float
    id: str | None
    inner: str
    vbW: float
    vbH: float
    scale: float
    rotationDeg: float


class RequestedItem(TypedDict, total=False):
    name: str
    quantity: int
    details: str


RoomRequirement = str


class Viewport(TypedDict):
    x: float
    y: float
    scale: float


@dataclass
class PlannerDraftOutput:
    walls: list[Wall]
    rooms: list[Room]
    assets: list[Asset]
    roomRequirements: list[RoomRequirement]
    view: Viewport | None = None
    prompt: str = ""
    notes: str = ""


__all__ = [
    "PlannerDraftOutput",
    "Viewport",
    "Wall",
    "Room",
    "Asset",
    "RoomRequirement",
    "RequestedItem",
    "Point",
]
