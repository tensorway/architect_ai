from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any


@dataclass(frozen=True)
class SvgAssetDefinition:
    name: str
    vbW: float
    vbH: float
    inner: str
    source_path: Path

    @property
    def key(self) -> str:
        return normalize_name(self.name)


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def parse_number(value: Any, default: float | None = None) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN guard
        return default
    return num


def parse_length_attr(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"[-+]?[0-9]*\\.?[0-9]+", raw)
    return float(match.group()) if match else None


def extract_viewbox(root: ET.Element) -> tuple[float, float]:
    vb_raw = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if vb_raw:
        parts = [p for p in re.split(r"[ ,]+", vb_raw.strip()) if p]
        if len(parts) >= 4:
            try:
                return float(parts[2]), float(parts[3])
            except ValueError:
                pass

    width = parse_length_attr(root.attrib.get("width"))
    height = parse_length_attr(root.attrib.get("height"))
    if width and height:
        return width, height
    return 100.0, 100.0


def strip_script_nodes(root: ET.Element) -> None:
    # xml.etree has no parent pointers; walk copies to remove safely.
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.split("}")[-1] if isinstance(child.tag, str) else ""
            if tag.lower() == "script":
                parent.remove(child)


def strip_namespaces(el: ET.Element) -> None:
    """Remove XML namespaces in-place so serialized tags are plain SVG."""
    for node in el.iter():
        if isinstance(node.tag, str) and "}" in node.tag:
            node.tag = node.tag.split("}", 1)[1]
        # drop xmlns* attributes
        for attr in list(node.attrib):
            if attr.startswith("xmlns"):
                node.attrib.pop(attr)


def parse_svg_asset(path: Path) -> SvgAssetDefinition:
    tree = ET.parse(path)
    root = tree.getroot()
    strip_script_nodes(root)
    strip_namespaces(root)
    vbW, vbH = extract_viewbox(root)
    allowed = {
        "g",
        "path",
        "rect",
        "circle",
        "line",
        "polyline",
        "polygon",
        "ellipse",
        "text",
        "use",
    }

    def keep(el: ET.Element) -> bool:
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        return tag in allowed

    inner_parts = [
        ET.tostring(child, encoding="unicode")
        for child in list(root)
        if keep(child)
    ]
    inner = "".join(inner_parts).strip()
    return SvgAssetDefinition(
        name=path.stem,
        vbW=vbW,
        vbH=vbH,
        inner=inner,
        source_path=path,
    )


def load_svg_catalog(models_dir: Path) -> dict[str, SvgAssetDefinition]:
    catalog: dict[str, SvgAssetDefinition] = {}
    for svg_path in sorted(models_dir.glob("*.svg")):
        asset = parse_svg_asset(svg_path)
        if not asset.inner:
            continue
        catalog[asset.key] = asset
    return catalog


def scale_for_width(vb_width: float, target_width_m: float) -> float:
    # 100 px per meter in the client canvas.
    if vb_width <= 0:
        return 1.0
    target_px = target_width_m * 100.0
    return target_px / vb_width
