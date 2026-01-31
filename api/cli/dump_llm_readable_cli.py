"""Generate an LLM-friendly textual dump of a workflow log.

This CLI mirrors ``workflow_log_cli`` in how it locates and parses the
workflow log, but writes a compact, line-based representation that keeps
values trimmed for language model consumption.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cli import workflow_log_cli


# Maximum number of characters to show for any field value.
DEFAULT_FIELD_WIDTH = 50


def _resolve_default_log_file() -> Path:
    # Reuse the resolution logic from the HTML workflow log generator.
    return workflow_log_cli._resolve_default_log_file()


def _compact(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cutoff = max(limit - 3, 0)
    return text[:cutoff] + "..."


def _stringify_value(value: Any, limit: int) -> str:
    if value is None:
        return "<none>"
    if isinstance(value, (bool, int, float, str)):
        text = str(value)
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = repr(value)

    text = " ".join(text.split())  # collapse whitespace to a single line
    return _compact(text, limit)


def _render_payload(label: str, payload: Any, prefix: str, limit: int) -> list[str]:
    lines: list[str] = []
    header = f"{prefix}{label}:"

    if payload is None:
        return [f"{header} <none>"]

    if isinstance(payload, dict):
        if not payload:
            return [f"{header} <empty>"]

        lines.append(header)
        for key, value in payload.items():
            value_text = _stringify_value(value, limit)
            lines.append(f"{prefix}  - {key}: {value_text}")
        return lines

    value_text = _stringify_value(payload, limit)
    return [f"{header} {value_text}"]


def _sort_children(node: workflow_log_cli.StepNode) -> None:
    node.children.sort(key=lambda child: child.record.index)
    for child in node.children:
        _sort_children(child)


def _render_node(
    node: workflow_log_cli.StepNode,
    prefix: str,
    is_last: bool,
    limit: int,
) -> list[str]:
    record = node.record
    connector = "" if not prefix else ("`--" if is_last else "|--")
    line_prefix = f"{prefix}{connector}"

    lines: list[str] = [
        f"{line_prefix}{record.step_class} [idx {record.index}] ({record.step_module})",
        f"{prefix}{'   ' if is_last else '|  '}ts: {record.timestamp}",
        f"{prefix}{'   ' if is_last else '|  '}uuid: {record.uuid}",
        f"{prefix}{'   ' if is_last else '|  '}caller: {record.caller_uuid or '-'}",
    ]

    body_prefix = prefix + ("   " if is_last else "|  ")
    lines.extend(_render_payload("input", record.input_value, body_prefix, limit))
    lines.extend(_render_payload("output", record.output_value, body_prefix, limit))

    children = node.children
    for idx, child in enumerate(children):
        child_prefix = prefix + ("   " if is_last else "|  ")
        lines.extend(_render_node(child, child_prefix, idx == len(children) - 1, limit))

    return lines


def _render_tree(roots: list[workflow_log_cli.StepNode], limit: int) -> str:
    lines: list[str] = []
    for idx, root in enumerate(roots):
        _sort_children(root)
        lines.extend(_render_node(root, "", idx == len(roots) - 1, limit))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_dump_llm_readable(
    log_path: Path | None, output_path: Path | None, limit: int
) -> Path:
    log_path = log_path or _resolve_default_log_file()

    if output_path is None:
        default_name = log_path.with_suffix("").name or "workflow_log"
        output_path = log_path.parent / f"{default_name}_dump_llm_readable.txt"

    records = workflow_log_cli._load_records(log_path)
    roots = workflow_log_cli._build_nodes(records)

    core_text = _render_tree(roots, limit)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(core_text, encoding="utf-8")
    print(f"LLM-readable dump written to: {output_path}")
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a compact, LLM-friendly text dump of a workflow log "
            "with field values truncated for readability."
        )
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
        help="Destination text file. Defaults to <log>_dump_llm_readable.txt in the log directory.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_FIELD_WIDTH,
        help="Maximum number of characters for each field value (default: 50).",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    write_dump_llm_readable(args.log, args.output, args.max_chars)


if __name__ == "__main__":
    main()
