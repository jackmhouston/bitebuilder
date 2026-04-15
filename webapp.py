#!/usr/bin/env python3
"""
Local BiteBuilder web UI.
"""

import json
import re
import subprocess
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, current_app, jsonify, render_template, request, send_from_directory

from bitebuilder import (
    build_candidate_shortlist,
    BiteBuilderError,
    build_validation_error,
    coerce_request_int,
    parse_premiere_xml_safe,
    validate_brief,
    format_error_for_log,
    normalize_segment_index,
    normalize_segment_indexes,
    run_pipeline,
)
from generator.xmeml import generate_sequence
from generator.timecode import estimate_duration_seconds, frames_to_tc, tc_to_frames
from llm.ollama_client import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_THINKING_MODE,
    DEFAULT_TIMEOUT,
    generate_text,
    normalize_thinking_mode,
    resolve_host,
)
from llm.prompts import CHAT_SYSTEM_PROMPT, build_chat_prompt
from parser.transcript import TranscriptSegment, format_for_llm, parse_transcript
from parser.transcript import TranscriptValidationError


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output" / "web"
CHAT_TRANSCRIPT_LIMIT = 12000
JOB_STORE = {}
JOB_LOCK = threading.Lock()
SOLAR_DEMO_SOURCES = [
    {
        "transcript_path": "/Volumes/Two Jackson/001_Transcode/transcripts/CEO Interview.txt",
        "xml_path": "/Volumes/Two Jackson/001_Transcode/transcripts/CEO-intv.xml",
        "label": "CEO Interview",
    },
    {
        "transcript_path": "/Volumes/Two Jackson/001_Transcode/transcripts/Technician Interview.txt",
        "xml_path": "/Volumes/Two Jackson/001_Transcode/transcripts/Technician Interview.xml",
        "label": "Technician Interview",
    },
]
SOLAR_DEMO_BRIEF = (
    "Innovation-forward 5-7 minute sequence built from interview bites. Open with the strongest positive proof point, "
    "not a negative objection. Emphasize first-in-California / forefront-of-technology positioning, then move into clear "
    "technician-led proof, then land on an insightful, future-facing resolution. Keep it modular, hooky, and editorially "
    "sharp. Avoid long boring selects. Do not shorten transcript text in any exported bite references."
)
SOLAR_DEMO_CONTEXT = (
    "This cut should feel like a real editor's working board, not a wizard or chatbot. The story direction already established is: "
    "1. positive innovation-forward opening 2. credibility / first-mover framing 3. technician-led technical proof in the middle "
    "4. optimistic close about clean energy, resilience, and future viability. Client/style notes: avoid opening on a negative bite; "
    "bring out the innovation; first people to do it in California; forefront of technology / space; solar survives / clean energy is not going away; "
    "keep exact transcript bite text and exact timecodes; favor modular, hooky phrasing over long intact selects."
)
SOLAR_DEMO_NOTES = (
    "Working editorial preference: selection-first browser workspace over unclear TUI; exact transcript fidelity matters; visible selected order matters; "
    "source A/B/many-source ingest should be simple; Python remains authoritative for parsing, validation, generation, and export; this UI should help shape a cut fast, not explain itself for 10 minutes."
)
SEGMENT_INDEX_PATTERN = re.compile(r"\[(\d+)\]")
TIMECODE_RANGE_PATTERN = re.compile(
    r"(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})"
)
TIMECODE_PATTERN = re.compile(r"\b\d{2}:\d{2}:\d{2}:\d{2}\b")
NARRATIVE_ARC_PATTERN = re.compile(r"narrative\s+arc[^:\n]*:\s*(.+)", re.IGNORECASE)
PROJECT_FILE_EXTENSIONS = (".bitebuilder-project.json", ".json")
APP_STEPS = (
    {
        "key": "intake",
        "label": "Upload",
        "path": "/",
    },
    {
        "key": "brief",
        "label": "Validate",
        "path": "/project/brief",
    },
    {
        "key": "chat",
        "label": "Preview/Confirm",
        "path": "/project/chat",
    },
    {
        "key": "generate",
        "label": "Generate",
        "path": "/project/generate",
    },
    {
        "key": "export",
        "label": "Download",
        "path": "/project/export",
    },
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validation_error_payload(
    code: str,
    error_type: str,
    message: str,
    expected_input_format: str,
    next_action: str,
    *,
    recoverable: bool = False,
    stage: str | None = None,
) -> dict:
    return build_validation_error(
        code=code,
        error_type=error_type,
        message=message,
        expected_input_format=expected_input_format,
        next_action=next_action,
        recoverable=recoverable,
        stage=stage,
    )


def transcript_timecode_error_payload(errors: list[dict], stage: str = "transcript") -> dict:
    return build_validation_error(
        code="TRANSCRIPT-TIMECODE-INVALID",
        error_type="invalid_transcript_content",
        message="Transcript timecodes are invalid or impossible.",
        expected_input_format="Timecoded transcript blocks as HH:MM:SS:FF - HH:MM:SS:FF in chronological order.",
        next_action=(
            "Fix transcript formatting issues at the listed lines and retry "
            "generation or chat."
        ),
        recoverable=True,
        stage=stage,
        details={"errors": errors},
    )


def validation_error_response(payload: dict, status: int = 400):
    current_app.logger.error("api_error=%s", format_error_for_log(payload))
    return jsonify({"status": "error", "error": payload}), status


def _source_value(source, key: str, default):
    if hasattr(source, key):
        return getattr(source, key)
    if hasattr(source, "to_dict"):
        try:
            source_dict = source.to_dict()
            if isinstance(source_dict, dict) and key in source_dict:
                return source_dict[key]
        except Exception:
            pass
    if isinstance(source, dict):
        return source.get(key, default)
    return default


def recoverable_generation_response(payload: dict, result: dict | None = None):
    response = {
        "status": payload.get("partial", {}).get("status") if isinstance(payload, dict) else "partial",
        "error": payload,
        "result": result,
    }
    return jsonify(response), 200


def preferred_model(models: list[str]) -> str:
    preferred_prefixes = (
        "gemma3:",
        "llama3.2:3b",
        "llama3.2:1b",
        "llama3.2:",
        "gemma4:e4b",
        "gemma4:",
        "llama3:",
        "qwen",
        "mistral",
    )
    excluded = ("resume-matcher", "embed", "nomic-embed")
    for prefix in preferred_prefixes:
        for model in models:
            lowered = model.lower()
            if lowered.startswith(prefix) and not any(bad in lowered for bad in excluded):
                return model
    for model in models:
        lowered = model.lower()
        if not any(bad in lowered for bad in excluded):
            return model
    return models[0] if models else DEFAULT_MODEL


def trim_transcript_for_chat(formatted_transcript: str) -> str:
    if len(formatted_transcript) <= CHAT_TRANSCRIPT_LIMIT:
        return formatted_transcript
    return (
        formatted_transcript[:CHAT_TRANSCRIPT_LIMIT]
        + "\n\n[Transcript preview truncated for chat. Generation still uses the full transcript.]"
    )


def resolve_repo_path(relative_path: str) -> Path:
    return (ROOT / relative_path).resolve()


def source_pair_error(message: str, *, code: str = "SOURCE-PAIR-INVALID", stage: str = "input", details: dict | None = None) -> BiteBuilderError:
    raise BiteBuilderError(build_validation_error(
        code=code,
        error_type="missing_inputs",
        message=message,
        expected_input_format="source_pairs as [{transcript_text, xml_text, transcript_name?, xml_name?}] with transcript/xml provided together.",
        next_action="Provide matching transcript/XML content for each source slot, or remove incomplete source slots.",
        recoverable=True,
        stage=stage,
        details=details or {},
    ))


def normalize_request_source_pairs(data: dict, *, require_xml: bool = True) -> list[dict]:
    raw_pairs = data.get("source_pairs")
    pairs = []
    if isinstance(raw_pairs, list) and raw_pairs:
        for index, raw in enumerate(raw_pairs):
            if not isinstance(raw, dict):
                source_pair_error(
                    "Each source pair must be an object.",
                    code="SOURCE-PAIR-TYPE-INVALID",
                    details={"index": index, "actual_type": type(raw).__name__},
                )
            transcript_text = (raw.get("transcript_text") or "").strip()
            xml_text = (raw.get("xml_text") or "").strip()
            if not transcript_text and not xml_text:
                continue
            if not transcript_text or not xml_text:
                if not require_xml and transcript_text and not xml_text and len(raw_pairs) == 1:
                    pairs.append({
                        "transcript_text": transcript_text,
                        "xml_text": "",
                        "transcript_name": (raw.get("transcript_name") or f"Source {index + 1} transcript").strip(),
                        "xml_name": (raw.get("xml_name") or "").strip(),
                    })
                    continue
                source_pair_error(
                    f"Source {index + 1} is incomplete.",
                    code="SOURCE-PAIR-INCOMPLETE",
                    details={"index": index, "has_transcript": bool(transcript_text), "has_xml": bool(xml_text)},
                )
            pairs.append({
                "transcript_text": transcript_text,
                "xml_text": xml_text,
                "transcript_name": (raw.get("transcript_name") or f"Source {index + 1} transcript").strip(),
                "xml_name": (raw.get("xml_name") or f"Source {index + 1} xml").strip(),
            })
    else:
        transcript_text = (data.get("transcript_text") or "").strip()
        xml_text = (data.get("xml_text") or "").strip()
        if transcript_text or xml_text:
            if not require_xml and transcript_text and not xml_text:
                pairs.append({
                    "transcript_text": transcript_text,
                    "xml_text": "",
                    "transcript_name": (data.get("transcript_name") or "Source 1 transcript").strip(),
                    "xml_name": "",
                })
            else:
                if not transcript_text or not xml_text:
                    source_pair_error(
                        "Transcript text and Premiere XML text are required together.",
                        code="SOURCE-PAIR-INCOMPLETE",
                        details={"index": 0, "has_transcript": bool(transcript_text), "has_xml": bool(xml_text)},
                    )
                pairs.append({
                    "transcript_text": transcript_text,
                    "xml_text": xml_text,
                    "transcript_name": (data.get("transcript_name") or "Source 1 transcript").strip(),
                    "xml_name": (data.get("xml_name") or "Source 1 xml").strip(),
                })
    return pairs


def xml_source_start_frame(xml_text: str) -> int:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return 0
    clip = root.find('.//clipitem')
    if clip is None:
        return 0
    clip_in = clip.findtext('in') or '0'
    try:
        return int(clip_in)
    except ValueError:
        return 0


def offset_segments(segments: list[TranscriptSegment], frame_offset: int, *, timebase: int) -> list[TranscriptSegment]:
    if frame_offset <= 0:
        return segments
    adjusted = []
    for segment in segments:
        start = tc_to_frames(segment.tc_in, timebase) + frame_offset
        end = tc_to_frames(segment.tc_out, timebase) + frame_offset
        adjusted.append(TranscriptSegment(
            tc_in=frames_to_tc(start, timebase),
            tc_out=frames_to_tc(end, timebase),
            speaker=segment.speaker,
            text=segment.text,
            start_line=segment.start_line,
            end_line=segment.end_line,
        ))
    return adjusted


def serialize_segments_as_transcript(segments: list[TranscriptSegment]) -> str:
    blocks = []
    for segment in segments:
        blocks.append(f"{segment.tc_in} - {segment.tc_out}\n{segment.speaker}\n{segment.text}".strip())
    return "\n\n".join(blocks)


def load_request_media(data: dict, *, require_xml: bool = True) -> dict:
    pairs = normalize_request_source_pairs(data, require_xml=require_xml)
    if not pairs:
        return {
            "pairs": [],
            "transcript_text": "",
            "xml_text": "",
            "source": None,
            "segments": [],
            "source_summaries": [],
        }

    primary = pairs[0]
    if not primary["xml_text"]:
        try:
            segments = parse_transcript(primary["transcript_text"], strict=True)
        except TranscriptValidationError as exc:
            raise BiteBuilderError(transcript_timecode_error_payload(exc.errors, "transcript")) from exc
        return {
            "pairs": pairs,
            "transcript_text": primary["transcript_text"],
            "xml_text": "",
            "source": None,
            "segments": segments,
            "source_summaries": [{
                "index": 0,
                "transcript_name": primary["transcript_name"],
                "xml_name": "",
                "offset_frames": 0,
                "pathurl": "",
                "segment_count": len(segments),
            }],
        }

    try:
        source = parse_premiere_xml_safe(primary["xml_text"])
    except Exception as exc:
        if isinstance(exc, BiteBuilderError):
            raise
        raise BiteBuilderError(validation_error_payload(
            code="SOURCE-PAIR-XML-INVALID",
            error_type="invalid_xml",
            message="Could not parse Premiere XML.",
            expected_input_format="Valid Premiere XML export text for each source.",
            next_action="Upload a fresh Premiere XML export for the failing source.",
            stage="premiere_xml",
            details={"cause": str(exc), "source_index": 0},
        )) from exc
    try:
        segments = parse_transcript(primary["transcript_text"], strict=True, timebase=source.timebase, ntsc=source.ntsc)
    except TranscriptValidationError as exc:
        raise BiteBuilderError(transcript_timecode_error_payload(exc.errors, "transcript")) from exc

    source_summaries = [{
        "index": 0,
        "transcript_name": primary["transcript_name"],
        "xml_name": primary["xml_name"],
        "offset_frames": 0,
        "pathurl": source.pathurl,
        "segment_count": len(segments),
    }]

    for index, pair in enumerate(pairs[1:], start=1):
        try:
            source_b = parse_premiere_xml_safe(pair["xml_text"])
        except Exception as exc:
            if isinstance(exc, BiteBuilderError):
                raise
            raise BiteBuilderError(validation_error_payload(
                code="SOURCE-PAIR-XML-INVALID",
                error_type="invalid_xml",
                message="Could not parse Premiere XML.",
                expected_input_format="Valid Premiere XML export text for each source.",
                next_action="Upload a fresh Premiere XML export for the failing source.",
                stage="premiere_xml",
                details={"cause": str(exc), "source_index": index},
            )) from exc
        if source_b.pathurl != source.pathurl:
            source_pair_error(
                "Multiple source pairs currently require all XMLs to point at the same underlying source media.",
                code="SOURCE-PAIR-MULTI-SOURCE-UNSUPPORTED",
                details={"primary_pathurl": source.pathurl, "secondary_pathurl": source_b.pathurl, "source_index": index},
            )
        try:
            secondary_segments = parse_transcript(pair["transcript_text"], strict=True, timebase=source_b.timebase, ntsc=source_b.ntsc)
        except TranscriptValidationError as exc:
            raise BiteBuilderError(transcript_timecode_error_payload(exc.errors, "transcript")) from exc
        offset_frames = xml_source_start_frame(pair["xml_text"])
        secondary_segments = offset_segments(secondary_segments, offset_frames, timebase=source.timebase)
        segments = sorted([*segments, *secondary_segments], key=lambda segment: tc_to_frames(segment.tc_in, source.timebase))
        source_summaries.append({
            "index": index,
            "transcript_name": pair["transcript_name"],
            "xml_name": pair["xml_name"],
            "offset_frames": offset_frames,
            "pathurl": source_b.pathurl,
            "segment_count": len(secondary_segments),
        })

    return {
        "pairs": pairs,
        "transcript_text": serialize_segments_as_transcript(segments),
        "xml_text": primary["xml_text"],
        "source": source,
        "segments": segments,
        "source_summaries": source_summaries,
    }


def build_page_context(
    page_key: str,
    page_title: str,
) -> dict:
    current_index = next(
        (index for index, step in enumerate(APP_STEPS) if step["key"] == page_key),
        0,
    )
    steps = []
    for index, step in enumerate(APP_STEPS):
        steps.append({
            **step,
            "active": step["key"] == page_key,
            "complete": index < current_index,
        })

    return {
        "steps": steps,
        "page_key": page_key,
        "page_title": page_title,
        "asset_version": max(
            int((ROOT / "static" / "app.css").stat().st_mtime_ns),
            int((ROOT / "static" / "app.js").stat().st_mtime_ns),
        ),
    }


def build_segment_lookup(segments) -> dict[tuple[str, str], dict]:
    lookup = {}
    for index, segment in enumerate(segments):
        lookup[(segment.tc_in, segment.tc_out)] = {
            "segment_index": index,
            "tc_in": segment.tc_in,
            "tc_out": segment.tc_out,
            "speaker": segment.speaker,
            "text": segment.text,
        }
    return lookup


def compact_text(text: str, limit: int = 180) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def extract_reply_segment_indexes(reply: str, segments) -> list[int]:
    indexes = []
    seen = set()

    for match in SEGMENT_INDEX_PATTERN.finditer(reply or ""):
        index = normalize_segment_index(match.group(1))
        if index is not None and 0 <= index < len(segments) and index not in seen:
            seen.add(index)
            indexes.append(index)

    tc_lookup = {
        segment.tc_in: index
        for index, segment in enumerate(segments)
    }
    range_lookup = {
        (segment.tc_in, segment.tc_out): index
        for index, segment in enumerate(segments)
    }

    for match in TIMECODE_RANGE_PATTERN.finditer(reply or ""):
        index = range_lookup.get((match.group(1), match.group(2)))
        if index is not None and index not in seen:
            seen.add(index)
            indexes.append(index)

    for match in TIMECODE_PATTERN.finditer(reply or ""):
        index = tc_lookup.get(match.group(0))
        if index is not None and index not in seen:
            seen.add(index)
            indexes.append(index)

    return indexes


def infer_plan_speaker_balance(segment_indexes: list[int], segments) -> str:
    if not segment_indexes:
        return "balanced"
    speaker_ones = 0
    speaker_others = 0
    for index in segment_indexes:
        if not (0 <= index < len(segments)):
            continue
        if segments[index].speaker == "Speaker 1":
            speaker_ones += 1
        else:
            speaker_others += 1
    if speaker_others > speaker_ones:
        return "worker"
    if speaker_ones > 0 and speaker_others == 0:
        return "ceo"
    return "balanced"


def infer_narrative_arc(reply: str, segment_indexes: list[int]) -> str:
    match = NARRATIVE_ARC_PATTERN.search(reply or "")
    if match:
        return compact_text(match.group(1), limit=120)
    if len(segment_indexes) >= 4:
        return "Hook -> Pivot -> Proof -> Vision"
    if len(segment_indexes) == 3:
        return "Hook -> Proof -> Close"
    if len(segment_indexes) == 2:
        return "Hook -> Pivot"
    return ""


def build_copilot_plan(reply: str, segments, messages: list[dict] | None = None) -> dict:
    indexes = extract_reply_segment_indexes(reply, segments)
    opening_index = indexes[0] if indexes else None
    must_include = indexes[:4]
    latest_user_message = ""
    for message in reversed(messages or []):
        if (message.get("role") or "").strip().lower() == "user":
            latest_user_message = (message.get("content") or "").strip()
            if latest_user_message:
                break

    directive_parts = []
    if opening_index is not None and 0 <= opening_index < len(segments):
        segment = segments[opening_index]
        directive_parts.append(
            f"Open on [{opening_index}] {segment.tc_in} - {segment.tc_out}: {compact_text(segment.text, 140)}"
        )
    if len(must_include) > 1:
        other_indexes = must_include[1:]
        directive_parts.append(
            "Keep these beats in the cut: " + ", ".join(f"[{value}]" for value in other_indexes)
        )
    narrative_arc = infer_narrative_arc(reply, must_include)
    if narrative_arc:
        directive_parts.append(f"Narrative arc: {narrative_arc}")
    if latest_user_message:
        directive_parts.append(f"Honor latest user direction: {compact_text(latest_user_message, 160)}")

    return {
        "opening_segment_index": opening_index,
        "must_include_segment_indexes": must_include,
        "generation_directive": " ".join(part for part in directive_parts if part),
        "narrative_arc": narrative_arc,
        "speaker_balance": infer_plan_speaker_balance(must_include, segments),
        "rationale": compact_text(reply, 320),
        "source_segment_indexes": indexes,
    }


def enrich_option(option: dict, segments, candidate_shortlist: list[dict] | None = None) -> dict:
    segment_lookup = build_segment_lookup(segments)
    candidate_lookup = {
        item["segment_index"]: item
        for item in (candidate_shortlist or [])
    }
    selected_cuts = []
    for cut in option.get("cuts", []):
        base = segment_lookup.get((cut["tc_in"], cut["tc_out"]), {})
        segment_index = base.get("segment_index")
        candidate = candidate_lookup.get(segment_index, {})
        selected_cuts.append({
            "segment_index": segment_index,
            "tc_in": cut["tc_in"],
            "tc_out": cut["tc_out"],
            "speaker": cut.get("speaker") or base.get("speaker", ""),
            "purpose": cut.get("purpose", ""),
            "dialogue_summary": cut.get("dialogue_summary", ""),
            "text": base.get("text", ""),
            "reasons": candidate.get("reasons", []),
            "roles": candidate.get("roles", []),
            "score": candidate.get("score"),
        })
    return {
        "name": option.get("name", ""),
        "description": option.get("description", ""),
        "estimated_duration_seconds": option.get("estimated_duration_seconds"),
        "selected_cuts": selected_cuts,
    }


def serialize_generation_result(run_id: str, run_dir: Path, result: dict) -> dict:
    response_options = result.get("response", {}).get("options", [])
    candidate_shortlist = result.get("debug_artifacts", {}).get("candidate_shortlist", [])
    enriched_options = [
        enrich_option(option, result.get("segments", []), candidate_shortlist)
        for option in response_options
    ]

    files = []
    for index, item in enumerate(result["output_files"]):
        option_payload = enriched_options[index] if index < len(enriched_options) else {
            "selected_cuts": [],
            "name": item["name"],
            "description": item["description"],
            "estimated_duration_seconds": item["estimated_duration_seconds"],
        }
        files.append({
            "name": item["name"],
            "description": item["description"],
            "filename": item["filename"],
            "cut_count": item["cut_count"],
            "actual_duration_seconds": item["actual_duration_seconds"],
            "estimated_duration_seconds": item["estimated_duration_seconds"],
            "download_url": f"/api/output/{run_id}/{item['filename']}",
            "selected_cuts": option_payload["selected_cuts"],
        })

    debug_urls = {
        key: f"/api/output/{run_id}/{Path(path).name}"
        for key, path in (result.get("debug_files") or {}).items()
    }

    return {
        "run_id": run_id,
        "saved_dir": str(run_dir),
        "segment_count": result["segment_count"],
        "run_metadata": result.get("run_metadata"),
        "source": result["source"].to_dict(),
        "thinking_mode": result["thinking_mode"],
        "target_duration_range": result["target_duration_range"],
        "validation_errors": result["validation_errors"],
        "used_retry": result.get("used_retry", False),
        "selection_retry": result.get("selection_retry", {}),
        "debug_download_url": f"/api/output/{run_id}/_llm_response.json",
        "debug_files": debug_urls,
        "candidate_shortlist": candidate_shortlist,
        "options_detail": enriched_options,
        "files": files,
    }


def open_output_path(path: Path) -> str:
    candidates = [
        ["xdg-open", str(path)],
        ["open", str(path)],
        ["explorer.exe", str(path)],
    ]
    errors = []
    for command in candidates:
        try:
            subprocess.Popen(command)
            return f"Opened {path}"
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or f"Could not open {path}")


def read_text_if_exists(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def build_solar_demo_payload() -> dict:
    source_pairs = []
    missing = []
    for source in SOLAR_DEMO_SOURCES:
        transcript_path = Path(source["transcript_path"])
        xml_path = Path(source["xml_path"])
        transcript_text = read_text_if_exists(transcript_path)
        xml_text = read_text_if_exists(xml_path)
        if not transcript_text or not xml_text:
            missing.append({
                "label": source["label"],
                "has_transcript": bool(transcript_text),
                "has_xml": bool(xml_text),
            })
            continue
        source_pairs.append({
            "transcript_text": transcript_text,
            "xml_text": xml_text,
            "transcript_name": transcript_path.name,
            "xml_name": xml_path.name,
            "label": source["label"],
        })
    if missing:
        raise BiteBuilderError(build_validation_error(
            code="SOLAR-DEMO-MISSING",
            error_type="missing_file",
            message="Could not load one or more solar demo source files.",
            expected_input_format="Mounted source files at the known solar demo paths.",
            next_action="Reconnect the source volume or choose files manually in the workspace.",
            stage="file",
            recoverable=True,
            details={"missing": missing},
        ))
    return {
        "project_title": "Solar innovation story",
        "variant_name": "solar-v1",
        "brief": SOLAR_DEMO_BRIEF,
        "project_context": SOLAR_DEMO_CONTEXT,
        "project_notes": SOLAR_DEMO_NOTES,
        "source_pairs": source_pairs,
    }


def apply_variant_name(result: dict, run_dir: Path, variant_name: str) -> None:
    variant = (variant_name or "").strip()
    if not variant:
        return
    safe_variant = variant.replace(" ", "_").replace("/", "-")
    for item in result.get("output_files", []):
        original = run_dir / item["filename"]
        new_filename = f"{safe_variant}__{item['filename']}"
        updated = run_dir / new_filename
        if original.exists() and original != updated:
            original.rename(updated)
        item["filename"] = new_filename
        item["path"] = str(updated)
        item["name"] = f"{variant} | {item['name']}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["OUTPUT_ROOT"] = OUTPUT_ROOT

    @app.get("/")
    def index():
        return render_template(
            "intake.html",
            **build_page_context(
                page_key="intake",
                page_title="Upload",
            ),
        )

    @app.get("/project/intake")
    def project_intake():
        return index()

    @app.get("/project/brief")
    def project_brief():
        return render_template(
            "context.html",
            **build_page_context(
                page_key="brief",
                page_title="Validate",
            ),
        )

    @app.get("/project/context")
    def project_context():
        return project_brief()

    @app.get("/project/chat")
    def project_chat():
        return render_template(
            "copilot.html",
            **build_page_context(
                page_key="chat",
                page_title="Preview/Confirm",
            ),
        )

    @app.get("/project/copilot")
    def project_copilot():
        return project_chat()

    @app.get("/project/generate")
    def project_generate():
        return render_template(
            "generate.html",
            **build_page_context(
                page_key="generate",
                page_title="Generate",
            ),
        )

    @app.get("/project/output")
    def project_output():
        return project_generate()

    @app.get("/workspace")
    def workspace():
        context = build_page_context(
            page_key="workspace",
            page_title="Workspace",
        )
        context["steps"] = []
        return render_template("workspace.html", **context)

    @app.get("/project/workspace")
    def project_workspace():
        return workspace()

    @app.get("/project/export")
    def project_export():
        return render_template(
            "export.html",
            **build_page_context(
                page_key="export",
                page_title="Export",
            ),
        )

    @app.get("/project/logs")
    def project_logs():
        return render_template(
            "logs.html",
            **build_page_context(
                page_key="logs",
                page_title="Logs",
            ),
        )

    @app.get("/api/models")
    def get_models():
        try:
            active_host, models = resolve_host(model=DEFAULT_MODEL, preferred_host=DEFAULT_HOST)
        except Exception:
            active_host, models = DEFAULT_HOST, []
        return jsonify({
            "connected": bool(models),
            "models": models,
            "default_model": preferred_model(models),
            "default_thinking_mode": normalize_thinking_mode(DEFAULT_THINKING_MODE),
            "host": active_host,
        })

    @app.get("/api/demo/solar-workspace")
    def solar_workspace_demo():
        if request.remote_addr not in {"127.0.0.1", "::1", None}:
            return validation_error_response(validation_error_payload(
                code="SOLAR-DEMO-LOCAL-ONLY",
                error_type="permission_denied",
                message="Solar demo preset is only available from localhost.",
                expected_input_format="Local browser session on the same machine as the Flask app.",
                next_action="Open the workspace locally or load sources manually.",
                stage="access",
            ), 403)
        try:
            payload = build_solar_demo_payload()
        except BiteBuilderError as exc:
            return validation_error_response(exc.error, 404)
        return jsonify(payload)

    @app.get("/repo-file/<path:repo_path>")
    def repo_file(repo_path: str):
        file_path = resolve_repo_path(repo_path)
        if ROOT not in file_path.parents or not file_path.is_file():
            return validation_error_response(validation_error_payload(
                code="REPO-FILE-MISSING",
                error_type="missing_file",
                message="Requested repo file was not found.",
                expected_input_format="A repo_path that maps to a file under project root.",
                next_action="Use a valid file path from the repository list.",
                stage="file",
            ), 404)
        return send_from_directory(file_path.parent, file_path.name, as_attachment=False)

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        try:
            media = load_request_media(data, require_xml=False)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        transcript_text = media["transcript_text"]
        if not transcript_text:
            return validation_error_response(validation_error_payload(
                code="CHAT-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required for chat.",
                expected_input_format="Request JSON must include transcript_text or source_pairs.",
                next_action="Upload transcript text before sending chat request.",
                stage="transcript",
            ))

        segments = media["segments"]
        if not segments:
            return validation_error_response(validation_error_payload(
                code="CHAT-TRANSCRIPT-NO-SEGMENTS",
                error_type="unsupported_file_content",
                message="No transcript segments were found in the transcript.",
                expected_input_format="At least one HH:MM:SS:FF - HH:MM:SS:FF segment with text.",
                next_action="Use a transcript export with timecoded segments.",
                stage="transcript",
            ))

        model = (data.get("model") or DEFAULT_MODEL).strip()
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        try:
            timeout = coerce_request_int(
                data.get("timeout"),
                field_name="timeout",
                default=DEFAULT_TIMEOUT,
                code="CHAT-TIMEOUT-INVALID",
                stage="chat",
            )
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        try:
            active_host, _ = resolve_host(model=model, preferred_host=DEFAULT_HOST)
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="CHAT-HOST-UNAVAILABLE",
                error_type="runtime_dependency",
                message="Could not connect to local model host.",
                expected_input_format="Reachable Ollama or llama-server host/port with model access.",
                next_action="Start the configured model runtime and check host port in /api/models.",
                stage="model",
                details={"cause": str(exc)},
            ))

        formatted_transcript = trim_transcript_for_chat(format_for_llm(segments))
        prompt = build_chat_prompt(
            formatted_transcript=formatted_transcript,
            brief=brief,
            project_context=project_context,
            messages=messages,
        )

        try:
            reply = generate_text(
                system_prompt=CHAT_SYSTEM_PROMPT,
                user_prompt=prompt,
                model=model,
                host=active_host,
                timeout=timeout,
                thinking_mode=thinking_mode,
            )
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="CHAT-LLM-FAILED",
                error_type="runtime_llm_error",
                message="Failed to generate chat guidance.",
                expected_input_format="Valid chat prompt and active model.",
                next_action="Verify model availability and retry.",
                stage="llm_generation",
                details={"cause": str(exc)},
            ))

        suggested_plan = build_copilot_plan(reply, segments, messages=messages)

        return jsonify({
            "reply": reply,
            "suggested_plan": suggested_plan,
            "segment_count": len(segments),
            "host": active_host,
        })

    @app.post("/api/parse-transcript")
    def parse_transcript_api():
        data = request.get_json(silent=True) or {}
        try:
            media = load_request_media(data)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        if not media["transcript_text"]:
            return validation_error_response(validation_error_payload(
                code="PARSE-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required.",
                expected_input_format="Request JSON with transcript_text or source_pairs.",
                next_action="Provide transcript text.",
                stage="transcript",
            ))
        source = media["source"]
        segments = media["segments"]
        return jsonify({
            "segment_count": len(segments),
            "source_count": len(media["source_summaries"]),
            "source_summaries": media["source_summaries"],
            "segments": [
                {
                    "segment_index": index,
                    "tc_in": segment.tc_in,
                    "tc_out": segment.tc_out,
                    "speaker": segment.speaker,
                    "text": segment.text,
                    "duration_seconds": estimate_duration_seconds(
                        segment.tc_in,
                        segment.tc_out,
                        source.timebase,
                        source.ntsc,
                    ),
                }
                for index, segment in enumerate(segments)
            ],
        })

    @app.post("/api/preview-shortlist")
    def preview_shortlist():
        data = request.get_json(silent=True) or {}
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()
        try:
            media = load_request_media(data)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        if not media["transcript_text"] or not media["xml_text"]:
            return validation_error_response(validation_error_payload(
                code="PREVIEW-INPUT-MISSING",
                error_type="missing_inputs",
                message="Transcript text and Premiere XML text are required.",
                expected_input_format="Both transcript_text/xml_text or complete source_pairs.",
                next_action="Fill both required fields before previewing candidates.",
                stage="input",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        source = media["source"]
        segments = media["segments"]
        if not segments:
            return validation_error_response(validation_error_payload(
                code="PREVIEW-TRANSCRIPT-NO-SEGMENTS",
                error_type="unsupported_file_content",
                message="No transcript segments were found.",
                expected_input_format="At least one timecoded block with text.",
                next_action="Use a transcript export with timecoded blocks.",
                stage="transcript",
            ))
        shortlist = build_candidate_shortlist(
            segments=segments,
            source=source,
            brief=validated_brief,
            project_context=project_context,
            editorial_messages=messages,
            accepted_plan=accepted_plan,
            pinned_segment_indexes=data.get("pinned_segment_indexes"),
            banned_segment_indexes=data.get("banned_segment_indexes"),
            required_segment_indexes=data.get("required_segment_indexes"),
            locked_segment_indexes=data.get("locked_segment_indexes"),
            forced_open_segment_index=data.get("forced_open_segment_index"),
            speaker_balance=speaker_balance,
        )
        return jsonify({"candidates": shortlist, "count": len(shortlist)})

    @app.post("/api/render-xml")
    def render_xml():
        data = request.get_json(silent=True) or {}
        option_name = (data.get("name") or "Manual Edit").strip()
        cuts = data.get("cuts") or []
        try:
            media = load_request_media(data)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        xml_text = media["xml_text"]
        transcript_text = media["transcript_text"]
        if not xml_text or not cuts:
            return validation_error_response(validation_error_payload(
                code="MANUAL-INPUT-MISSING",
                error_type="missing_inputs",
                message="Premiere XML and at least one cut are required.",
                expected_input_format="xml_text + cuts array.",
                next_action="Provide both values and retry.",
                stage="input",
            ))

        try:
            segments = parse_transcript(transcript_text, strict=True) if transcript_text else []
        except TranscriptValidationError as exc:
            return validation_error_response(transcript_timecode_error_payload(exc.errors, "transcript"), 400)
        segment_lookup = build_segment_lookup(segments)
        try:
            source = parse_premiere_xml_safe(xml_text)
        except Exception as exc:
            if isinstance(exc, BiteBuilderError):
                return validation_error_response(exc.error, 400)
            return validation_error_response(build_validation_error(
                code="MANUAL-XML-INVALID",
                error_type="invalid_xml",
                message="Could not parse Premiere XML for manual render.",
                expected_input_format="Valid raw Premiere XML export.",
                next_action="Upload valid XML and retry.",
                stage="premiere_xml",
                details={"cause": str(exc)},
            ))

        normalized_cuts = []
        for item in cuts:
            if "tc_in" in item and "tc_out" in item:
                normalized_cuts.append({"tc_in": item["tc_in"], "tc_out": item["tc_out"]})
                continue
            segment_index = normalize_segment_index(item.get("segment_index"))
            if segment_index is None or segment_index >= len(segments):
                continue
            segment = segments[segment_index]
            normalized_cuts.append({"tc_in": segment.tc_in, "tc_out": segment.tc_out})

        if not normalized_cuts:
            return validation_error_response(validation_error_payload(
                code="MANUAL-NO-VALID-CUTS",
                error_type="invalid_cuts",
                message="No valid cuts were provided.",
                expected_input_format="At least one cut as tc_in/tc_out or valid segment_index.",
                next_action="Send corrected cut entries referencing parsed transcript segments.",
                stage="cuts",
            ))

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        xml_str = generate_sequence(name=option_name, cuts=normalized_cuts, source=source)
        filename = f"{option_name.replace(' ', '_').replace('/', '-')}.xml"
        filepath = run_dir / filename
        filepath.write_text(xml_str, encoding="utf-8")
        cuts_detail = []
        for cut in normalized_cuts:
            base = segment_lookup.get((cut["tc_in"], cut["tc_out"]), {})
            cuts_detail.append({
                "tc_in": cut["tc_in"],
                "tc_out": cut["tc_out"],
                "speaker": base.get("speaker", ""),
                "text": base.get("text", ""),
            })

        payload = {
            "run_id": run_id,
            "saved_dir": str(run_dir),
            "files": [{
                "name": option_name,
                "filename": filename,
                "download_url": f"/api/output/{run_id}/{filename}",
                "selected_cuts": cuts_detail,
            }],
            "debug_files": {},
            "validation_errors": [],
        }
        (run_dir / "_manual_selection.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return jsonify(payload)

    @app.post("/api/open-output-folder")
    def open_output_folder():
        data = request.get_json(silent=True) or {}
        run_id = (data.get("run_id") or "").strip()
        saved_dir = (data.get("saved_dir") or "").strip()
        target = None
        if run_id:
            target = app.config["OUTPUT_ROOT"] / run_id
        elif saved_dir:
            target = Path(saved_dir)
        if not target:
            return validation_error_response(validation_error_payload(
                code="OPEN-OUTPUT-MISSING",
                error_type="missing_inputs",
                message="run_id or saved_dir is required.",
                expected_input_format="Either run_id (queued response) or saved_dir path.",
                next_action="Pass run_id or absolute saved_dir from generation responses.",
                stage="output",
            ))
        try:
            message = open_output_path(target.resolve())
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="OPEN-OUTPUT-FAILED",
                error_type="runtime_output_error",
                message="Could not open output folder.",
                expected_input_format="Writable output directory path.",
                next_action="Confirm folder exists and OS permissions allow opening.",
                stage="output",
                details={"cause": str(exc)},
            ))
        return jsonify({"message": message})

    @app.get("/api/session-log/<run_id>")
    def session_log(run_id: str):
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        log_path = run_dir / "_generation_log.json"
        payload = {
            "run_id": run_id,
            "saved_dir": str(run_dir),
            "generation_log": json.loads(read_text_if_exists(log_path) or "{}"),
            "llm_response": json.loads(read_text_if_exists(run_dir / "_llm_response.json") or "{}"),
            "prompt_text": read_text_if_exists(run_dir / "_generation_prompt.txt"),
            "editorial_direction": read_text_if_exists(run_dir / "_editorial_direction.txt"),
            "candidate_shortlist": json.loads(read_text_if_exists(run_dir / "_candidate_shortlist.json") or "[]"),
        }
        return jsonify(payload)

    @app.post("/api/generate")
    def generate():
        data = request.get_json(silent=True) or {}
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        model = (data.get("model") or DEFAULT_MODEL).strip()
        try:
            options = coerce_request_int(
                data.get("options"),
                field_name="options",
                default=3,
                code="GENERATE-OPTIONS-INVALID",
                stage="generation",
            )
            timeout = coerce_request_int(
                data.get("timeout"),
                field_name="timeout",
                default=DEFAULT_TIMEOUT,
                code="GENERATE-TIMEOUT-INVALID",
                stage="generation",
            )
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        variant_name = (data.get("variant_name") or "").strip()
        pinned_segment_indexes = normalize_segment_indexes(data.get("pinned_segment_indexes"))
        banned_segment_indexes = normalize_segment_indexes(data.get("banned_segment_indexes"))
        required_segment_indexes = normalize_segment_indexes(data.get("required_segment_indexes"))
        locked_segment_indexes = normalize_segment_indexes(data.get("locked_segment_indexes"))
        forced_open_segment_index = normalize_segment_index(data.get("forced_open_segment_index"))
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()
        try:
            media = load_request_media(data)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        transcript_text = media["transcript_text"]
        xml_text = media["xml_text"]

        if not transcript_text:
            return validation_error_response(validation_error_payload(
                code="GENERATE-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required.",
                expected_input_format="Transcript key in request JSON.",
                next_action="Provide transcript content before generation.",
                stage="transcript",
            ))
        if not xml_text:
            return validation_error_response(validation_error_payload(
                code="GENERATE-XML-MISSING",
                error_type="invalid_xml",
                message="Premiere XML text is required.",
                expected_input_format="xml_text key in request JSON.",
                next_action="Provide Premiere XML content before generation.",
                stage="premiere_xml",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = run_pipeline(
                transcript_text=transcript_text,
                xml_text=xml_text,
                brief=validated_brief,
                options=options,
                model=model,
                output_dir=str(run_dir),
                host=DEFAULT_HOST,
                timeout=timeout,
                project_context=project_context,
                editorial_messages=messages,
                accepted_plan=accepted_plan,
                pinned_segment_indexes=pinned_segment_indexes,
                banned_segment_indexes=banned_segment_indexes,
                required_segment_indexes=required_segment_indexes,
                locked_segment_indexes=locked_segment_indexes,
                forced_open_segment_index=forced_open_segment_index,
                speaker_balance=speaker_balance,
                thinking_mode=thinking_mode,
            )
        except Exception as exc:
            if isinstance(exc, BiteBuilderError) and exc.error.get("partial"):
                return recoverable_generation_response(exc.error)
            if isinstance(exc, BiteBuilderError):
                app.logger.error("generation_failed=%s", format_error_for_log(exc.error))
                return validation_error_response(exc.error)
            return validation_error_response(validation_error_payload(
                code="GENERATE-FAILED",
                error_type="runtime_failure",
                message="Generation failed.",
                expected_input_format="Valid transcript, XML, brief, and model connection.",
                next_action="Retry after fixing input errors shown above.",
                stage="generation",
                details={"cause": str(exc)},
            ))

        apply_variant_name(result, run_dir, variant_name)
        return jsonify(serialize_generation_result(run_id, run_dir, result))

    @app.post("/api/generate-jobs")
    def generate_jobs():
        data = request.get_json(silent=True) or {}
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        model = (data.get("model") or DEFAULT_MODEL).strip()
        try:
            options = coerce_request_int(
                data.get("options"),
                field_name="options",
                default=3,
                code="GENERATE-JOB-OPTIONS-INVALID",
                stage="generation",
            )
            timeout = coerce_request_int(
                data.get("timeout"),
                field_name="timeout",
                default=DEFAULT_TIMEOUT,
                code="GENERATE-JOB-TIMEOUT-INVALID",
                stage="generation",
            )
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        variant_name = (data.get("variant_name") or "").strip()
        pinned_segment_indexes = normalize_segment_indexes(data.get("pinned_segment_indexes"))
        banned_segment_indexes = normalize_segment_indexes(data.get("banned_segment_indexes"))
        required_segment_indexes = normalize_segment_indexes(data.get("required_segment_indexes"))
        locked_segment_indexes = normalize_segment_indexes(data.get("locked_segment_indexes"))
        forced_open_segment_index = normalize_segment_index(data.get("forced_open_segment_index"))
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()
        try:
            media = load_request_media(data)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        transcript_text = media["transcript_text"]
        xml_text = media["xml_text"]

        if not transcript_text or not xml_text or not brief:
            return validation_error_response(validation_error_payload(
                code="GENERATE-JOB-INPUT-MISSING",
                error_type="missing_inputs",
                message="Transcript text, Premiere XML, and a brief are required.",
                expected_input_format="transcript_text, xml_text, brief in JSON request.",
                next_action="Supply all required values before starting job.",
                stage="input",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)

        job_id = uuid4().hex
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        def update_job(message: str, status: str | None = None, payload: dict | None = None):
            with JOB_LOCK:
                job = JOB_STORE[job_id]
                job["logs"].append({"timestamp": now_iso(), "message": message})
                if status:
                    job["status"] = status
                if payload is not None:
                    job["result"] = payload

        with JOB_LOCK:
            JOB_STORE[job_id] = {
                "job_id": job_id,
                "run_id": run_id,
                "status": "queued",
                "logs": [{"timestamp": now_iso(), "message": "Queued generation job."}],
                "result": None,
                "error": None,
            }

        def worker():
            try:
                update_job("Starting generation.", status="running")
                result = run_pipeline(
                    transcript_text=transcript_text,
                    xml_text=xml_text,
                    brief=validated_brief,
                    options=options,
                    model=model,
                    output_dir=str(run_dir),
                    host=DEFAULT_HOST,
                    timeout=timeout,
                    project_context=project_context,
                    editorial_messages=messages,
                    accepted_plan=accepted_plan,
                    pinned_segment_indexes=pinned_segment_indexes,
                    banned_segment_indexes=banned_segment_indexes,
                    required_segment_indexes=required_segment_indexes,
                    locked_segment_indexes=locked_segment_indexes,
                    forced_open_segment_index=forced_open_segment_index,
                    speaker_balance=speaker_balance,
                    thinking_mode=thinking_mode,
                    progress_callback=lambda message: update_job(message),
                )
                apply_variant_name(result, run_dir, variant_name)
                payload = serialize_generation_result(run_id, run_dir, result)
                update_job("Generation complete.", status="completed", payload=payload)
            except Exception as exc:
                with JOB_LOCK:
                    if isinstance(exc, BiteBuilderError) and exc.error.get("partial"):
                        JOB_STORE[job_id]["status"] = "partial"
                        JOB_STORE[job_id]["error"] = exc.error
                        JOB_STORE[job_id]["logs"].append({
                            "timestamp": now_iso(),
                            "message": exc.error.get("message"),
                        })
                        return
                with JOB_LOCK:
                    JOB_STORE[job_id]["status"] = "error"
                    if isinstance(exc, BiteBuilderError):
                        error = exc.error
                        app.logger.error("job_error=%s", format_error_for_log(error))
                        JOB_STORE[job_id]["error"] = error
                        JOB_STORE[job_id]["logs"].append({"timestamp": now_iso(), "message": error.get("message", str(exc))})
                    else:
                        JOB_STORE[job_id]["error"] = str(exc)
                        JOB_STORE[job_id]["logs"].append({"timestamp": now_iso(), "message": str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"job_id": job_id, "run_id": run_id, "status": "queued"})

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        with JOB_LOCK:
            job = JOB_STORE.get(job_id)
        if not job:
            return validation_error_response(validation_error_payload(
                code="JOB-NOT-FOUND",
                error_type="missing_resource",
                message="Job not found.",
                expected_input_format="A valid job_id returned by /api/generate-jobs.",
                next_action="Request status for an existing job_id.",
                stage="job_status",
            ), 404)
        payload = {
            "job_id": job["job_id"],
            "run_id": job["run_id"],
            "status": job["status"],
            "logs": job["logs"],
            "error": job["error"],
        }
        if job["status"] == "completed":
            payload["result"] = job["result"]
        return jsonify(payload)

    @app.get("/api/output/<run_id>/<path:filename>")
    def download_output(run_id: str, filename: str):
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        return send_from_directory(run_dir, filename, as_attachment=True)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
