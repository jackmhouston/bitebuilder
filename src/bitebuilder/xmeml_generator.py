from __future__ import annotations

import xml.etree.ElementTree as ET

from bitebuilder.models import PremiereProject, SelectionCandidate, SourceClip


def render_xmeml_sequence(
    sequence_title: str,
    project: PremiereProject,
    selections: list[SelectionCandidate],
) -> str:
    root = ET.Element("xmeml", {"version": "4"})
    sequence = ET.SubElement(root, "sequence", {"id": "bitebuilder-sequence-1"})
    ET.SubElement(sequence, "name").text = sequence_title
    _append_rate(sequence, project.fps)
    ET.SubElement(sequence, "duration").text = "0"

    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    track = ET.SubElement(video, "track")

    timeline_cursor = 0
    for index, selection in enumerate(selections, start=1):
        source_clip = _match_source_clip(project, selection, index)
        duration_frames = _duration_to_frames(selection.duration_seconds, project.fps)
        clipitem = ET.SubElement(track, "clipitem", {"id": f"generated-clipitem-{index}"})
        ET.SubElement(clipitem, "name").text = source_clip.name
        ET.SubElement(clipitem, "enabled").text = "TRUE"
        _append_rate(clipitem, project.fps)
        ET.SubElement(clipitem, "start").text = str(timeline_cursor)
        ET.SubElement(clipitem, "end").text = str(timeline_cursor + duration_frames)
        ET.SubElement(clipitem, "in").text = str(source_clip.in_frame)
        ET.SubElement(clipitem, "out").text = str(source_clip.in_frame + duration_frames)
        if source_clip.masterclip_id:
            ET.SubElement(clipitem, "masterclipid").text = source_clip.masterclip_id

        if source_clip.file_id or source_clip.path_url or source_clip.file_name:
            file_node = ET.SubElement(
                clipitem,
                "file",
                {"id": source_clip.file_id or f"generated-file-{index}"},
            )
            if source_clip.file_name:
                ET.SubElement(file_node, "name").text = source_clip.file_name
            if source_clip.path_url:
                ET.SubElement(file_node, "pathurl").text = source_clip.path_url

        comments = ET.SubElement(clipitem, "comments")
        ET.SubElement(comments, "comment").text = selection.reason

        timeline_cursor += duration_frames

    sequence.find("./duration").text = str(timeline_cursor)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root,
        encoding="unicode",
    )


def _append_rate(node: ET.Element, fps: int) -> None:
    rate = ET.SubElement(node, "rate")
    ET.SubElement(rate, "timebase").text = str(fps)
    ET.SubElement(rate, "ntsc").text = "FALSE"


def _duration_to_frames(duration_seconds: float | None, fps: int) -> int:
    if duration_seconds is None:
        return fps * 4
    return max(int(duration_seconds * fps), fps)


def _match_source_clip(
    project: PremiereProject,
    selection: SelectionCandidate,
    fallback_index: int,
) -> SourceClip:
    if selection.source_clip_id:
        for clip in project.clips:
            if clip.clip_id == selection.source_clip_id:
                return clip
    if selection.source_clip_name:
        wanted = selection.source_clip_name.casefold()
        for clip in project.clips:
            if clip.name.casefold() == wanted:
                return clip
    return project.clips[(fallback_index - 1) % len(project.clips)]

