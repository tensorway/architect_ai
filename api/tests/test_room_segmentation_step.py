import math
import os
import sys
from pathlib import Path
import unittest

# Ensure the api package is importable when tests are run from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimal env so logging does not require real credentials.
os.environ.setdefault("MODEL_API_KEY", "test-key")
os.environ.setdefault("WORKFLOW_LOG_FILE", "/tmp/architect_ai_workflow_test.log")

from agent.workflow_steps.room_segmentation_step import (  # noqa: E402
    RoomSegmentationInput,
    RoomSegmentationStep,
)


def _contains_points(vertices, expected, tol=1e-6):
    remaining = set(range(len(expected)))
    for vx, vy in vertices:
        for idx in list(remaining):
            ex, ey = expected[idx]
            if math.hypot(vx - ex, vy - ey) <= tol:
                remaining.remove(idx)
                break
    return not remaining


class RoomSegmentationStepTest(unittest.TestCase):
    def test_single_rectangle_returns_one_room(self):
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            {"id": "w4", "a": {"x": 0, "y": 8}, "b": {"x": 0, "y": 0}},
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls))

        self.assertEqual(len(outputs), 1)
        rooms = outputs[0].rooms or []

        self.assertEqual(len(rooms), 1)
        room = rooms[0]
        verts = [(p["x"], p["y"]) for p in room["vertices"]]
        self.assertEqual(len(verts), 4)
        self.assertTrue(_contains_points(verts, [(0, 0), (10, 0), (10, 8), (0, 8)]))
        self.assertAlmostEqual(room["area"], 80.0, places=5)

    def test_rectangle_split_into_two_rooms(self):
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            {"id": "w4", "a": {"x": 0, "y": 8}, "b": {"x": 0, "y": 0}},
            {"id": "w5", "a": {"x": 5, "y": 0}, "b": {"x": 5, "y": 8}},  # divider
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls))

        self.assertEqual(len(outputs), 2)

        areas = sorted(room["area"] for out in outputs for room in out.rooms or [])
        self.assertAlmostEqual(areas[0], 40.0, places=5)
        self.assertAlmostEqual(areas[1], 40.0, places=5)

    def test_open_shape_returns_no_rooms(self):
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            # Missing closing wall on the left side
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls))
        self.assertEqual(len(outputs), 0)

    def test_open_gap_returns_no_rooms(self):
        # Same rectangle but last wall ends slightly short, leaving a gap.
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            {"id": "w4", "a": {"x": 0, "y": 8}, "b": {"x": 0.2, "y": 0.5}},  # gap to origin
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls, snap_eps=1e-4))

        self.assertEqual(len(outputs), 0)

    def test_diagonal_split_produces_two_triangles(self):
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            {"id": "w4", "a": {"x": 0, "y": 8}, "b": {"x": 0, "y": 0}},
            {"id": "w5", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 8}},  # diagonal
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls))

        self.assertEqual(len(outputs), 2)
        areas = sorted(room["area"] for out in outputs for room in out.rooms or [])
        self.assertAlmostEqual(areas[0], 40.0, places=5)
        self.assertAlmostEqual(areas[1], 40.0, places=5)

    def test_min_area_filters_sliver(self):
        walls = [
            {"id": "w1", "a": {"x": 0, "y": 0}, "b": {"x": 10, "y": 0}},
            {"id": "w2", "a": {"x": 10, "y": 0}, "b": {"x": 10, "y": 8}},
            {"id": "w3", "a": {"x": 10, "y": 8}, "b": {"x": 0, "y": 8}},
            {"id": "w4", "a": {"x": 0, "y": 8}, "b": {"x": 0, "y": 0}},
            {"id": "w5", "a": {"x": 0.1, "y": 0}, "b": {"x": 0.1, "y": 8}},  # narrow sliver
        ]

        outputs = RoomSegmentationStep().run(RoomSegmentationInput(walls=walls, min_area=1.0))

        # sliver (0.8 m^2) removed; main room remains
        self.assertEqual(len(outputs), 1)
        rooms = outputs[0].rooms or []
        self.assertEqual(len(rooms), 1)
        self.assertAlmostEqual(rooms[0]["area"], 79.2, places=4)


if __name__ == "__main__":
    unittest.main()
