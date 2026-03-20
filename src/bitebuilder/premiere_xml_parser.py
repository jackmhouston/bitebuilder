from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from bitebuilder.models import PremiereProject, SourceClip


def parse_premiere_xml(path: str | Path) -> PremiereProject:
    source_path = Path(path).expanduser().resolve()
    tree = ET.parse(source_path)
    root = tree.getroot()
    _strip_namespaces(root)

    fps = _extract_fps(root)
    sequence_name = _find_text(root, "./sequence/name") or source_path.stem
    clips: list[SourceClip] = []

    for index, clip_node in enumerate(root.findall(".//clipitem"), start=1):
        file_node = clip_node.find("./file")
        clip = SourceClip(
            clip_id=clip_node.get("id") or f"clipitem-{index}",
            name=_find_text(clip_node, "./name") or f"Clip {index}",
            file_id=file_node.get("id") if file_node is not None else None,
            file_name=_find_text(clip_node, "./file/name"),
            path_url=_find_text(clip_node, "./file/pathurl"),
            masterclip_id=_find_text(clip_node, "./masterclipid"),
            start_frame=_safe_int(_find_text(clip_node, "./start")),
            end_frame=_safe_int(_find_text(clip_node, "./end")),
            in_frame=_safe_int(_find_text(clip_node, "./in")),
            out_frame=_safe_int(_find_text(clip_node, "./out")),
        )
        clips.append(clip)

    if not clips:
        raise ValueError(f"No <clipitem> nodes found in {source_path}")

    return PremiereProject(
        source_path=source_path,
        sequence_name=sequence_name,
        fps=fps,
        clips=clips,
    )


def _extract_fps(root: ET.Element) -> int:
    sequence_timebase = _find_text(root, "./sequence/rate/timebase")
    if sequence_timebase and sequence_timebase.isdigit():
        return int(sequence_timebase)

    first_timebase = _find_text(root, ".//rate/timebase")
    if first_timebase and first_timebase.isdigit():
        return int(first_timebase)
    return 30


def _find_text(node: ET.Element, xpath: str) -> str | None:
    child = node.find(xpath)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _safe_int(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def _strip_namespaces(root: ET.Element) -> None:
    for node in root.iter():
        if "}" in node.tag:
            node.tag = node.tag.rsplit("}", 1)[1]

