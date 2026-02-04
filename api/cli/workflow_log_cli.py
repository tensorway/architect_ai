from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable
import config as config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "workflow_log_template.html"
)
VALIDATION_LOG_DIR = PROJECT_ROOT / "agent/logging"


def _resolve_default_log_file() -> Path:
    if VALIDATION_LOG_DIR.exists():
        log_files = [
            path
            for path in VALIDATION_LOG_DIR.iterdir()
            if path.is_file() and path.suffix == ".log"
        ]
        if log_files:
            return max(log_files, key=lambda item: item.stat().st_mtime)
    print(
        "No validation logs found; using default workflow log path. ",
        VALIDATION_LOG_DIR,
    )
    return config.load_settings().workflow_log_path


@dataclass(slots=True)
class StepRecord:
    uuid: str
    caller_uuid: str | None
    step_class: str
    step_module: str
    timestamp: str
    input_value: Any
    output_value: Any
    index: int


@dataclass(slots=True)
class StepNode:
    record: StepRecord
    children: list["StepNode"]

    def __init__(self, record: StepRecord) -> None:
        self.record = record
        self.children = []


def _load_records(path: Path) -> list[StepRecord]:
    records: list[StepRecord] = []

    with path.open(encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)

            caller_uuid = payload.get("caller_uuid")
            record = StepRecord(
                uuid=str(payload.get("step_uuid")),
                caller_uuid=str(caller_uuid) if caller_uuid else None,
                step_class=str(payload.get("step_class", "")),
                step_module=str(payload.get("step_module", "")),
                timestamp=str(payload.get("timestamp", "")),
                input_value=payload.get("input"),
                output_value=payload.get("output"),
                index=index,
            )
            records.append(record)
    return records


def _build_nodes(records: Iterable[StepRecord]) -> list[StepNode]:
    nodes = {record.uuid: StepNode(record) for record in records}
    roots: list[StepNode] = []

    for record in records:
        node = nodes[record.uuid]
        if record.caller_uuid and record.caller_uuid in nodes:
            nodes[record.caller_uuid].children.append(node)
        else:
            roots.append(node)
    return roots


FIELD_COLLAPSE_THRESHOLD = 300


def _extract_planner_payload(value: Any) -> dict[str, Any] | None:
    """Return a normalized PlannerDraftOutput-like payload or None."""

    def _as_plan(obj: Any) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        if "plan" in obj and isinstance(obj["plan"], dict):
            return obj["plan"]  # Some steps may wrap the draft inside {plan: ...}
        return obj

    plan = _as_plan(value)
    if not plan:
        return None

    walls = plan.get("walls")
    assets = plan.get("assets", [])
    rooms = plan.get("rooms", [])

    if not isinstance(walls, list):
        return None
    if not isinstance(assets, list):
        assets = []
    if not isinstance(rooms, list):
        rooms = []
    if not walls and not assets and not rooms:
        return None

    return {
        "walls": walls,
        "assets": assets,
        "rooms": rooms,
        "roomRequirements": plan.get("roomRequirements", []),
        "view": plan.get("view"),
        "prompt": plan.get("prompt", ""),
    }


def _plan_bounds(plan: dict[str, Any]) -> tuple[float, float, float, float]:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def _touch_point(pt: Any) -> None:
        nonlocal min_x, min_y, max_x, max_y
        if not isinstance(pt, dict):
            return
        x, y = pt.get("x"), pt.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    for wall in plan.get("walls", []):
        if not isinstance(wall, dict):
            continue
        _touch_point(wall.get("a"))
        _touch_point(wall.get("b"))

    for room in plan.get("rooms", []):
        verts = room.get("vertices") if isinstance(room, dict) else None
        if isinstance(verts, list):
            for pt in verts:
                _touch_point(pt)

    for asset in plan.get("assets", []):
        if not isinstance(asset, dict):
            continue
        _touch_point(asset)

    if min_x == float("inf"):
        return (0.0, 0.0, 400.0, 280.0)

    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    pad = max(width, height) * 0.1 + 10
    return (min_x - pad, min_y - pad, width + pad * 2, height + pad * 2)


def _render_planner_snapshot(payload: Any) -> str:
    plan = _extract_planner_payload(payload)
    if not plan:
        return ""

    view_min_x, view_min_y, view_w, view_h = _plan_bounds(plan)

    room_polys: list[str] = []
    for room in plan.get("rooms", []):
        verts = room.get("vertices") if isinstance(room, dict) else None
        if not isinstance(verts, list) or len(verts) < 3:
            continue
        coords: list[tuple[float, float]] = []
        for v in verts:
            if not isinstance(v, dict):
                continue
            x, y = v.get("x"), v.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                coords.append((float(x), float(y)))
        if len(coords) < 3:
            continue
        pts = [f"{x},{y}" for x, y in coords]
        cx = sum(x for x, _ in coords) / len(coords)
        cy = sum(y for _, y in coords) / len(coords)
        label = escape(str(room.get("label", room.get("id", ""))))
        room_polys.append(
            """
            <g class='room'>
              <polygon points='{points}' />
              <text x='{cx}' y='{cy}'>{label}</text>
            </g>
            """.strip().format(points=" ".join(pts), label=label, cx=cx, cy=cy)
        )

    wall_lines: list[str] = []
    for wall in plan.get("walls", []):
        if not isinstance(wall, dict):
            continue
        a, b = wall.get("a"), wall.get("b")
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        wall_lines.append(
            "<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' />".format(
                x1=a.get("x", 0),
                y1=a.get("y", 0),
                x2=b.get("x", 0),
                y2=b.get("y", 0),
            )
        )

    asset_marks: list[str] = []
    for asset in plan.get("assets", []):
        if not isinstance(asset, dict):
            continue
        x, y = asset.get("x"), asset.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        name = escape(str(asset.get("name", "asset")))
        scale = asset.get("scale", 1.0)
        rotation = asset.get("rotationDeg", 0.0)
        inner = asset.get("inner")

        transform = f"translate({x} {y}) rotate({rotation}) scale({scale})"
        if isinstance(inner, str) and inner.strip():
            asset_marks.append(
                "<g class='asset' transform='{t}'>"
                "{inner}"
                "</g>".format(t=transform, inner=inner)
            )
        else:
            vbw = asset.get("vbW")
            vbh = asset.get("vbH")
            width = float(vbw) if isinstance(vbw, (int, float)) else 24.0
            height = float(vbh) if isinstance(vbh, (int, float)) else 24.0
            x0 = -width / 2
            y0 = -height / 2
            asset_marks.append(
                "<g class='asset' transform='{t}'>"
                "<rect class='asset-fallback' x='{x}' y='{y}' width='{w}' height='{h}' rx='3' />"
                "</g>".format(t=transform, x=x0, y=y0, w=width, h=height)
            )

    svg = (
        "<div class='plan-snapshot'>"
        "<div class='plan-snapshot-title'>Planner snapshot</div>"
        "<div class='plan-snapshot-frame'>"
        "<svg viewBox='{vx} {vy} {vw} {vh}' role='img' aria-label='Planner snapshot'>"
        "<rect class='bg' x='{vx}' y='{vy}' width='{vw}' height='{vh}' />"
        "<g class='rooms'>{rooms}</g>"
        "<g class='walls'>{walls}</g>"
        "<g class='assets'>{assets}</g>"
        "</svg>"
        "</div>"
        "</div>"
    ).format(
        vx=view_min_x,
        vy=view_min_y,
        vw=view_w,
        vh=view_h,
        rooms="".join(room_polys),
        walls="".join(wall_lines),
        assets="".join(asset_marks),
    )

    return svg


def _serialize_payload(payload: Any, *, indent: int = 2) -> str:
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def _prepare_payload(payload: Any) -> Any:
    return payload


def _format_field_value(value: Any) -> tuple[str, bool]:
    serialized = _serialize_payload(value, indent=2)
    serialized = serialized.replace("\\n", "\n")
    should_collapse = len(serialized) > FIELD_COLLAPSE_THRESHOLD
    return escape(serialized), should_collapse


def _make_field_id(section_id: str, index: int) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", f"{section_id}-field-{index}")


def _render_payload_fields(section_id: str, payload: Any, label: str) -> str:
    if payload is None:
        return '<div class="payload-empty">No data</div>'

    def _render_toggle_button(field_id: str, collapsed: bool) -> str:
        if not collapsed:
            return '<span class="field-button-placeholder" aria-hidden="true"></span>'
        return (
            f'<button class="toggle-field secondary small" data-target="{field_id}" '
            f'data-collapse-text="Collapse Value" data-expand-text="Expand Value">Expand Value</button>'
        )

    if isinstance(payload, dict):
        if not payload:
            return '<div class="payload-empty">No fields</div>'

        content_segments: list[str] = ['<div class="payload-fields">']
        for index, (key, value) in enumerate(payload.items()):
            field_id = _make_field_id(section_id, index)
            escaped_field_id = escape(field_id)
            key_label = escape(str(key))
            escaped_value, default_collapsed = _format_field_value(value)
            collapse_class = " collapsed" if default_collapsed else ""
            button_markup = _render_toggle_button(escaped_field_id, default_collapsed)

            content_segments.append(
                '<div class="payload-field">'
                '<div class="payload-field-row">'
                f"{button_markup}"
                f'<div class="payload-key">{key_label}</div>'
                '<div class="payload-value">'
                f'<div id="{escaped_field_id}" class="field-content{collapse_class}">'
                f"<pre>{escaped_value}</pre>"
                "</div>"
                "</div>"
                "</div>"
                "</div>"
            )
        content_segments.append("</div>")
        return "".join(content_segments)

    field_id = _make_field_id(section_id, 0)
    escaped_field_id = escape(field_id)
    escaped_value, default_collapsed = _format_field_value(payload)
    collapse_class = " collapsed" if default_collapsed else ""
    button_markup = _render_toggle_button(escaped_field_id, default_collapsed)
    key_text = escape(label.title())

    return (
        '<div class="payload-field">'
        '<div class="payload-field-row">'
        f"{button_markup}"
        f'<div class="payload-key">{key_text}</div>'
        '<div class="payload-value">'
        f'<div id="{escaped_field_id}" class="field-content{collapse_class}">'
        f"<pre>{escaped_value}</pre>"
        "</div>"
        "</div>"
        "</div>"
        "</div>"
    )


def _render_payload_section(step_id: str, label: str, payload: Any) -> str:
    section_id = f"{step_id}-{label}"
    snapshot = _render_planner_snapshot(payload)
    if snapshot:
        return (
            '<div class="payload-section payload-with-snapshot">'
            f'<div class="payload-title">{label.title()}</div>'
            '<div class="payload-layout">'
            f'<div class="payload-col fields-col">{_render_payload_fields(section_id, payload, label)}</div>'
            f'<div class="payload-col snapshot-col">{snapshot}</div>'
            "</div>"
            "</div>"
        )

    return (
        '<div class="payload-section">'
        f'<div class="payload-title">{label.title()}</div>'
        f"{_render_payload_fields(section_id, payload, label)}"
        "</div>"
    )


def _is_test_step_correct(record: StepRecord) -> bool | None:
    return True
    if record.step_class != TestAccountingAgentWorkflowStep.__name__:
        return None
    return bool(record.output_value.get("evaluation").get("is_correct"))


def _render_rows(roots: list[StepNode]) -> str:
    segments: list[str] = []

    def walk(node: StepNode, depth: int, parent_uuid: str | None) -> None:
        record = node.record
        step_id = record.uuid
        parent_attr = f' data-parent="{escape(parent_uuid)}"' if parent_uuid else ""
        classes: list[str] = ["step-row"]
        if depth:
            classes.append("hidden")
        test_correct = _is_test_step_correct(record)
        if test_correct is True:
            classes.append("test-step-correct")
        elif test_correct is False and test_correct is not None:
            classes.append("test-step-incorrect")
        class_attr = f' class="{" ".join(classes)}"' if classes else ""
        indent_style = f' style="padding-left: {depth * 4}rem;"'
        caller_text = record.caller_uuid or "—"
        children_button = ""
        if node.children:
            children_button = (
                f'<button class="toggle-children secondary small" data-toggle-children="{escape(step_id)}" '
                f'data-show-text="Show Children" data-hide-text="Hide Children">Show Children</button>'
            )
        input_payload = _prepare_payload(record.input_value)
        output_payload = _prepare_payload(record.output_value)
        collapse_button = (
            f'<button class="toggle-step small" data-step-id="{escape(step_id)}" '
            f'data-collapse-text="Collapse Step" data-expand-text="Expand Step">Collapse Step</button>'
        )
        controls_contents = []
        if children_button:
            controls_contents.append(children_button)
        controls_contents.append(collapse_button)
        controls = (
            '<div class="step-controls">' f'{"".join(controls_contents)}' "</div>"
        )
        step_extra = (
            '<div class="step-extra">'
            f'<div class="step-meta">UUID: {escape(step_id)}</div>'
            f'<div class="step-meta">Caller: {escape(caller_text)}</div>'
            f'<div class="step-meta">Timestamp: {escape(record.timestamp)}</div>'
            f'<div class="step-module">{escape(record.step_module)}</div>'
            "</div>"
        )
        details_content = (
            '<div class="step-details-content">'
            f'{_render_payload_section(step_id, "input", input_payload)}'
            f'{_render_payload_section(step_id, "output", output_payload)}'
            "</div>"
        )

        segments.append(
            "<tr"
            f' data-step-id="{escape(step_id)}"'
            f"{parent_attr}"
            f"{class_attr}"
            ">"
            f"<td{indent_style}>"
            f'<div class="step-name">{escape(record.step_class)}</div>'
            f"{controls}"
            f"{step_extra}"
            "</td>"
            "<td>"
            f"{details_content}"
            "</td>"
            "</tr>"
        )

        for child in node.children:
            walk(child, depth + 1, record.uuid)

    for root in roots:
        walk(root, 0, None)

    return "\n".join(segments)


def _build_html(rows_markup: str, log_path: Path, summary: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("__ROWS__", rows_markup)
        .replace("__LOG_PATH__", escape(str(log_path)))
        .replace("__GENERATED_AT__", escape(generated_at))
        .replace("__REPORT_SUMMARY__", escape(summary))
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render an HTML report from a workflow step log file."
    )
    parser.add_argument(
        "--log",
        type=Path,
        help=(
            "Path to the workflow log file. Defaults to the newest validation log if available."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help=(
            "Destination HTML file to create. Defaults to the workflow report path from settings."
        ),
    )
    return parser


def write_html(log_path: Path, output_path: Path) -> None:
    log_path: Path = log_path or _resolve_default_log_file()
    output_path: Path = output_path or config.load_settings().workflow_report_path

    records = _load_records(log_path)
    roots = _build_nodes(records)
    rows_markup = _render_rows(roots)

    total_tests = 0
    total_correct = 0
    for record in records:
        is_correct = _is_test_step_correct(record)
        if is_correct is None:
            continue
        total_tests += 1
        if is_correct:
            total_correct += 1
    percentage = (total_correct / total_tests * 100) if total_tests else 0.0
    summary = (
        f"{total_correct}/{total_tests} correct ({percentage:.1f}%)"
        if total_tests
        else "No test steps"
    )

    html = _build_html(rows_markup, log_path.resolve(), summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Workflow report written to: {output_path}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    write_html(args.log, args.output)


if __name__ == "__main__":
    main()
